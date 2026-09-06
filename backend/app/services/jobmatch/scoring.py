"""五维评分-确定性公式（docs/07-§6，M7.2）。

经验匹配度 25（实习相关度10/实践深度9/行业认知6）
技能匹配度 25（JD技能覆盖率10/熟练度9/工具链完整度6）
项目质量   25（项目复杂度9/个人角色9/成果量化7）
差异化竞争力 15（稀缺技能证书6/跨领域背景5/可量化成果4）
成长潜力   10（学习轨迹4/自我驱动3/可塑性3）

权重档位：default 25/25/25/15/10；bigtech 20/20/25/25/10；state 30/20/15/5/20。
等级：S≥85 / A≥70 / B≥55 / C<55。
LLM 只提供证据（evidence.py），本模块全部确定性计算。
"""
from __future__ import annotations

import re
import time
import uuid
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import CertScarcity, JdLibrary, ToolchainTemplate
from .matching import load_categories, load_ontology, scan_certs, scan_skills, track_sim

# ---------- 进程级缓存（岗位库技能频次/证书稀缺度：TTL 60s，避免每次评分全表扫描） ----------

_RARITY_TTL = 60.0
_rarity_cache: tuple[float, Counter, int] | None = None  # (ts, freq, n_jds)
_scarcity_cache: tuple[float, dict[str, int]] | None = None

WEIGHT_TIERS: dict[str, dict[str, int]] = {
    "default": {"experience_match": 25, "skill_match": 25, "project_quality": 25, "differentiation": 15, "growth_potential": 10},
    "bigtech": {"experience_match": 20, "skill_match": 20, "project_quality": 25, "differentiation": 25, "growth_potential": 10},
    "state": {"experience_match": 30, "skill_match": 20, "project_quality": 15, "differentiation": 5, "growth_potential": 20},
}
TIER_LABELS: dict[str, str] = {
    "default": "默认（综合）",
    "bigtech": "大厂/高竞争",
    "state": "国企/传统行业",
}
DIM_MAX: dict[str, float] = {
    "experience_match": 25.0,
    "skill_match": 25.0,
    "project_quality": 25.0,
    "differentiation": 15.0,
    "growth_potential": 10.0,
}
DIM_LABELS: dict[str, str] = {
    "experience_match": "经验匹配度",
    "skill_match": "技能匹配度",
    "project_quality": "项目质量",
    "differentiation": "差异化竞争力",
    "growth_potential": "成长潜力",
}

_DEPTH_LEAD = {"独立负责", "主导", "从0到1", "核心", "独立"}
_DEPTH_FOLLOW = {"参与", "协助", "跟进", "辅助"}
_ROLE_LEAD = {"主导", "独立负责", "从0到1", "设计", "搭建", "核心", "独立"}
_ROLE_FOLLOW = {"参与", "协助", "辅助", "支持"}
_DEPTH_WORDS = {"算法", "架构", "性能优化", "分布式", "高并发", "微服务", "容器化", "安全", "推荐", "大模型", "多模块", "跨团队"}
_SCALE_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*([万亿千万百]+)")
_NARRATIVE_WORDS = ("自学", "复盘", "主动", "连续学习", "跨领域", "快速学习", "自驱", "坚持")
_STABILITY_WORDS = ("党员", "学生干部", "志愿者", "志愿服务", "学生会")


def suggest_tier(jd_title: str, industry: str | None) -> str:
    """档位自动建议：量化/投行/大模型/推荐算法 → 大厂；银行/国企/管培 → 国企；其余默认。"""
    t = jd_title or ""
    ind = industry or ""
    if any(h in t for h in ("量化", "投行", "大模型", "推荐算法")):
        return "bigtech"
    if any(h in t for h in ("银行", "国企", "事业", "政府", "管培")):
        return "state"
    if "金融" in ind and "风控" in t:
        return "bigtech"
    return "default"


def _cap(v: float, top: float) -> float:
    return max(0.0, min(v, top))


# ---------- 维度一：经验匹配度 ----------


def _exp_internship_relevance(evidence: dict[str, Any], jd_leaf_id: uuid.UUID | None, idx) -> float:
    tracks = [
        (it.get("track") or "").strip()
        for it in evidence.get("internships") or []
        if (it.get("track") or "").strip() and it.get("track") != "其他"
    ]
    if not tracks:
        return 0.0
    return track_sim(tracks, jd_leaf_id, idx) * 10.0 if jd_leaf_id else 7.0


def _exp_depth(evidence: dict[str, Any]) -> float:
    best = 0.0
    for it in evidence.get("internships") or []:
        score = 0.0
        try:
            months = int(it.get("duration_months") or 0)
        except (TypeError, ValueError):
            months = 0
        score += 3.0 if months >= 6 else (2.0 if months >= 3 else (1.0 if months >= 1 else 0.0))
        kws = {str(k) for k in (it.get("depth_keywords") or [])}
        if kws & _DEPTH_LEAD:
            score += 3.0
        elif kws & _DEPTH_FOLLOW:
            score += 1.0
        if it.get("has_output"):
            score += 3.0
        best = max(best, score)
    return _cap(best, 9.0)


def _exp_cognition(evidence: dict[str, Any], extra_signals: list[str] | None = None) -> float:
    cog = evidence.get("industry_cognition") or {}
    try:
        judged = int(cog.get("judged_level") or 0)
    except (TypeError, ValueError):
        judged = 0
    signals = set(cog.get("signals") or [])
    for w in extra_signals or []:
        signals.add(w)
    return _cap(judged, 3.0) + _cap(len(signals), 3.0)


# ---------- 维度二：技能匹配度 ----------


def _skill_coverage(resume_skills: set[str], jd_core: list[str]) -> float:
    if not jd_core:
        return 5.0  # 中性
    hit = resume_skills & set(jd_core)
    return _cap(len(hit) / len(jd_core) * 10.0, 10.0)


def _skill_proficiency(evidence: dict[str, Any]) -> float:
    skills = [s for s in evidence.get("skills") or [] if s.get("skill")]
    if not skills:
        return 0.0
    core = [s for s in skills if s.get("is_core")] or skills
    total = 0.0
    for s in core:
        try:
            total += float(s.get("evidence_level") or 0)
        except (TypeError, ValueError):
            total += 0.0
    return _cap(total / len(core) * 9.0, 9.0)


def _skill_toolchain(resume_skills: set[str], toolchain: list[str] | None) -> float:
    if not toolchain:
        return 3.0  # 中性
    hit = resume_skills & set(toolchain)
    return _cap(len(hit) / len(toolchain) * 6.0, 6.0)


# ---------- 维度三：项目质量 ----------


def _proj_complexity(evidence: dict[str, Any]) -> float:
    best = 0.0
    for p in evidence.get("projects") or []:
        score = 0.0
        text = " ".join(
            str(x) for x in [p.get("quant_text"), *(p.get("complexity_signals") or [])] if x
        )
        m = _SCALE_RE.search(text)
        if m:
            unit = m.group(2)
            score += 4.0 if unit in ("亿",) else (3.0 if unit in ("千万", "百万") else (2.0 if unit in ("十万", "万") else 1.0))
        signals = {str(s) for s in (p.get("complexity_signals") or [])}
        depth = min(3.0, len(signals & _DEPTH_WORDS) + len(signals - _DEPTH_WORDS) * 0.5)
        tools = [str(t) for t in (p.get("tools") or []) if t]
        bonus = 2.0 if len(tools) >= 5 else 0.0
        score += depth + bonus
        best = max(best, score)
    return _cap(best, 9.0)


def _proj_role(evidence: dict[str, Any]) -> float:
    projects = [p for p in evidence.get("projects") or []]
    if not projects:
        return 0.0
    total = 0.0
    for p in projects:
        kws = {str(k) for k in (p.get("role_keywords") or [])}
        if kws & _ROLE_LEAD:
            total += 9.0
        elif kws & _ROLE_FOLLOW:
            total += 4.0
        else:
            total += 1.0
    return _cap(total / len(projects), 9.0)


def _proj_quant(evidence: dict[str, Any]) -> float:
    best = 0.0
    for p in evidence.get("projects") or []:
        if not p.get("quantified"):
            continue
        tools = [str(t) for t in (p.get("tools") or []) if t]
        verbs = [str(v) for v in (p.get("action_verbs") or []) if v]
        best = max(best, 7.0 if (tools and verbs) else 3.0)
    # 疑点降档
    doubts = " ".join(str(d) for d in (evidence.get("doubt_flags") or []))
    if "量化" in doubts or "数字" in doubts:
        best = 3.0 if best >= 7.0 else (0.0 if best >= 3.0 else best)
    return best


# ---------- 维度四：差异化竞争力 ----------


def _diff_cert_rarity(resume_certs: set[str], scarcity_map: dict[str, int], rarity: float) -> float:
    cert_score = 0.0
    if resume_certs:
        best = max((scarcity_map.get(c, 1) for c in resume_certs), default=1)
        cert_score = min(6.0, best + 1.0)
    rarity_score = _cap(rarity * 2.0, 2.0)
    return _cap(cert_score + rarity_score, 6.0)


def _diff_cross(evidence: dict[str, Any]) -> float:
    learning = evidence.get("learning") or {}
    cross = learning.get("cross_domain") or {}
    score = 3.0 if cross.get("dual_degree") or cross.get("minor") else 0.0
    if cross.get("related"):
        score += 2.0
    return _cap(score, 5.0)


def _diff_quant(evidence: dict[str, Any]) -> float:
    n = sum(1 for p in evidence.get("projects") or [] if p.get("quantified"))
    return 4.0 if n >= 3 else (3.0 if n == 2 else (2.0 if n == 1 else 0.0))


# ---------- 维度五：成长潜力 ----------


def _growth_learning(evidence: dict[str, Any], parsed_text: str) -> float:
    learning = evidence.get("learning") or {}
    score = 0.0
    if learning.get("github_active"):
        score += 2.0
    if learning.get("has_blog"):
        score += 1.0
    if learning.get("course_timeline"):
        score += 1.0
    return _cap(score, 4.0)


def _growth_self_driven(evidence: dict[str, Any]) -> float:
    items = [x for x in (evidence.get("learning") or {}).get("self_driven") or [] if x]
    return _cap(len(items), 3.0)


def _growth_plasticity(evidence: dict[str, Any], parsed_text: str) -> float:
    learning = evidence.get("learning") or {}
    cross = learning.get("cross_domain") or {}
    score = 1.5 if cross.get("related") else 0.0
    low = (parsed_text or "").lower()
    hits = sum(1 for w in _NARRATIVE_WORDS if w in low)
    score += min(1.5, hits * 0.5)
    return _cap(score, 3.0)


# ---------- 主入口 ----------


async def compute_five_dim_scores(
    session: AsyncSession,
    parsed: dict[str, Any],
    parsed_text: str,
    evidence: dict[str, Any],
    jd: JdLibrary,
    tier: str,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """五维评分（确定性），返回 {dimensions, total, level, tier, doubts}。

    cfg 为校准配置（calibration.get_config）；None 时用内置默认。
    """
    if tier not in WEIGHT_TIERS:
        tier = "default"
    # 校准配置解析
    thresholds = {"S": 85, "A": 70, "B": 55}
    cert_overrides: dict[str, int] = {}
    extra_signals: list[str] = []
    tier_weights_override: dict[str, int] | None = None
    if cfg:
        thr = cfg.get("level_thresholds") or {}
        thresholds = {k: thr.get(k, thresholds[k]) for k in thresholds}
        cert_overrides = cfg.get("cert_scarcity") or {}
        sw = (cfg.get("signal_words") or {}).get("industry_cognition") or []
        extra_signals = [str(w) for w in sw if w and w in (parsed_text or "")]
        tier_weights_override = (cfg.get("tier_weights") or {}).get(tier)
    idx = await load_categories(session)
    ontology = await load_ontology(session)

    # 简历技能/证书（证据 + 本地扫描兜底）
    resume_skills: set[str] = set()
    for s in evidence.get("skills") or []:
        if s.get("skill"):
            resume_skills.add(str(s["skill"]))
    resume_skills |= set(str(s) for s in (parsed.get("skills") or []))
    resume_skills |= scan_skills(parsed_text, ontology)
    resume_certs: set[str] = set()
    for c in evidence.get("certs") or []:
        if c.get("name"):
            resume_certs.add(str(c["name"]))
    resume_certs |= set(str(c) for c in (parsed.get("certs") or []))
    resume_certs |= scan_certs(parsed_text, ontology)

    # JD 侧
    jd_parsed = jd.jd_parsed or {}
    jd_core = [str(s) for s in (jd_parsed.get("skills") or [])]
    toolchain_row = (
        await session.scalar(
            select(ToolchainTemplate).where(ToolchainTemplate.category_id == jd.category_id)
        )
        if jd.category_id
        else None
    )
    toolchain = (toolchain_row.toolchain if toolchain_row else None) or None

    # 技能稀缺度（岗位库逆频率）
    rarity = await _skill_rarity(session, resume_skills, ontology)
    scarcity_map = await _cert_scarcity_map(session, cert_overrides)

    # ---------- 分项 ----------
    b_exp_relevance = _exp_internship_relevance(evidence, jd.category_id, idx)
    b_exp_depth = _exp_depth(evidence)
    b_exp_cognition = _exp_cognition(evidence, extra_signals)
    exp_score = _cap(b_exp_relevance + b_exp_depth + b_exp_cognition, 25.0)

    b_skill_cov = _skill_coverage(resume_skills, jd_core)
    b_skill_prof = _skill_proficiency(evidence)
    b_skill_tool = _skill_toolchain(resume_skills, toolchain)
    skill_score = _cap(b_skill_cov + b_skill_prof + b_skill_tool, 25.0)

    b_proj_complex = _proj_complexity(evidence)
    b_proj_role = _proj_role(evidence)
    b_proj_quant = _proj_quant(evidence)
    proj_score = _cap(b_proj_complex + b_proj_role + b_proj_quant, 25.0)

    b_diff_cert = _diff_cert_rarity(resume_certs, scarcity_map, rarity)
    b_diff_cross = _diff_cross(evidence)
    b_diff_quant = _diff_quant(evidence)
    diff_score = _cap(b_diff_cert + b_diff_cross + b_diff_quant, 15.0)

    b_growth_learn = _growth_learning(evidence, parsed_text)
    b_growth_drive = _growth_self_driven(evidence)
    b_growth_plastic = _growth_plasticity(evidence, parsed_text)
    growth_score = _cap(b_growth_learn + b_growth_drive + b_growth_plastic, 10.0)

    # 稳定性附加（党员/学生干部/志愿服务，+2 封顶，计入经验匹配度）
    stability_hits = sum(1 for w in _STABILITY_WORDS if w in parsed_text)
    exp_score = _cap(exp_score + min(2.0, stability_hits * 1.0), 25.0)

    raw = {
        "experience_match": exp_score,
        "skill_match": skill_score,
        "project_quality": proj_score,
        "differentiation": diff_score,
        "growth_potential": growth_score,
    }
    breakdown = {
        "experience_match": {
            "实习相关度": round(b_exp_relevance, 1),
            "实践深度": round(b_exp_depth, 1),
            "行业认知": round(b_exp_cognition, 1),
        },
        "skill_match": {
            "JD技能覆盖率": round(b_skill_cov, 1),
            "熟练度(证据层)": round(b_skill_prof, 1),
            "工具链完整度": round(b_skill_tool, 1),
        },
        "project_quality": {
            "项目复杂度": round(b_proj_complex, 1),
            "个人角色": round(b_proj_role, 1),
            "成果量化": round(b_proj_quant, 1),
        },
        "differentiation": {
            "稀缺技能/证书": round(b_diff_cert, 1),
            "跨领域背景": round(b_diff_cross, 1),
            "可量化成果": round(b_diff_quant, 1),
        },
        "growth_potential": {
            "学习轨迹": round(b_growth_learn, 1),
            "自我驱动": round(b_growth_drive, 1),
            "可塑性": round(b_growth_plastic, 1),
        },
    }

    # 档位加权 → 总分
    weights = tier_weights_override or WEIGHT_TIERS[tier]
    total = 0.0
    for dim, score in raw.items():
        normalized = score / DIM_MAX[dim] * 100.0
        total += normalized * weights[dim] / 100.0
    total = round(total, 1)

    level = (
        "S 强烈推荐"
        if total >= thresholds["S"]
        else ("A 推荐" if total >= thresholds["A"] else ("B 待定" if total >= thresholds["B"] else "C 需补强"))
    )

    return {
        "dimensions": {
            dim: {
                "label": DIM_LABELS[dim],
                "score": round(score, 1),
                "max": DIM_MAX[dim],
                "breakdown": breakdown[dim],
            }
            for dim, score in raw.items()
        },
        "total_score": total,
        "max_score": 100.0,
        "level": level,
        "tier": tier,
        "tier_label": TIER_LABELS[tier],
        "doubts": [str(d) for d in (evidence.get("doubt_flags") or [])],
        "hit_skills": sorted(resume_skills & set(jd_core))[:12],
        "missing_skills": sorted(set(jd_core) - resume_skills)[:12],
    }


async def _skill_rarity(session: AsyncSession, resume_skills: set[str], ontology) -> float:
    """技能稀缺度：岗位库中出现频率的逆频率（0-1 归一化取最高）。全表频次统计带 60s 进程级缓存。"""
    global _rarity_cache
    now = time.monotonic()
    if _rarity_cache is not None and now - _rarity_cache[0] < _RARITY_TTL:
        freq, n_jds = _rarity_cache[1], _rarity_cache[2]
    else:
        jds = (
            (
                await session.execute(
                    select(JdLibrary).where(JdLibrary.is_active == True)  # noqa: E712
                )
            )
            .scalars()
            .all()
        )
        if not jds:
            return 0.0
        freq: Counter = Counter()
        for jd in jds:
            parsed = jd.jd_parsed or {}
            core = {str(s) for s in (parsed.get("skills") or [])}
            if core:
                freq.update(core)
            else:
                freq.update(scan_skills(jd.jd_text, ontology))
        n_jds = len(jds)
        _rarity_cache = (now, freq, n_jds)
    if not freq:
        return 0.0
    best = 0.0
    for skill in resume_skills:
        f = freq.get(skill, 0) / n_jds
        if f == 0:
            # 技能完全未出现在岗位库：与目标岗位无关性未知，给中性值而非满分
            # （避免"简历里某个冷门技能"反而确定性拿满差异化加分）
            rarity = 0.5
        else:
            rarity = 1.0 - f
        best = max(best, rarity)
    return best


async def _cert_scarcity_map(session: AsyncSession, overrides: dict[str, int] | None = None) -> dict[str, int]:
    global _scarcity_cache
    now = time.monotonic()
    if _scarcity_cache is None or now - _scarcity_cache[0] >= _RARITY_TTL:
        rows = (await session.execute(select(CertScarcity))).scalars().all()
        mapping = {r.cert_name: r.scarcity_score for r in rows}
        _scarcity_cache = (now, mapping)
    else:
        mapping = dict(_scarcity_cache[1])
    for name, score in (overrides or {}).items():
        mapping[name] = int(score)
    return mapping
