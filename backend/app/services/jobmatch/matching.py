"""简历 → 岗位推荐匹配（docs/07-§5，M7.1）。

流程：硬过滤（学历）→ TF-IDF 粗筛（本地，零 LLM 成本）→ 结构化精排：
  match_score = 0.6 × struct_score + 0.4 × cosine×100

struct_score：技能覆盖率 50% / 教育匹配 20% / 赛道匹配 20% / 证书匹配 10%。
M7.4 可把 TF-IDF 余弦替换为向量检索（pgvector），接口不变。
"""
from __future__ import annotations

import math
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import CertScarcity, JdCategory, JdLibrary, JdSkillOntology
from .tokenize import tokenize_with_skills

# ---------- 进程级缓存（本体/分类树低频变化；JD 分词按 updated_at 失效） ----------

_CACHE_TTL = 60.0
_ontology_cache: tuple[float, "OntologyData"] | None = None
_categories_cache: tuple[float, "CategoryIndex"] | None = None
_JD_TOKENS: dict[uuid.UUID, tuple[str, list[str]]] = {}


def clear_match_cache() -> None:
    """清空本体/分类/分词缓存（运维/测试用）。"""
    global _ontology_cache, _categories_cache
    _ontology_cache = None
    _categories_cache = None
    _JD_TOKENS.clear()

# ---------- 数据结构 ----------


@dataclass
class OntologyData:
    skill_terms: list[str] = field(default_factory=list)  # 规范名+别名，全小写
    skill_names: list[dict] = field(default_factory=list)  # [{canonical, aliases}]
    cert_terms: list[str] = field(default_factory=list)
    cert_names: list[dict] = field(default_factory=list)


@dataclass
class CategoryIndex:
    nodes: dict[uuid.UUID, JdCategory] = field(default_factory=dict)
    by_name: dict[str, JdCategory] = field(default_factory=dict)  # 叶子按名


# ---------- 本体加载与技能扫描 ----------


async def load_ontology(session: AsyncSession) -> OntologyData:
    global _ontology_cache
    now = time.monotonic()
    if _ontology_cache is not None and now - _ontology_cache[0] < _CACHE_TTL:
        return _ontology_cache[1]
    rows = (
        (await session.execute(select(JdSkillOntology))).scalars().all()
    )
    data = OntologyData()
    for r in rows:
        aliases = [str(a).strip().lower() for a in (r.aliases or []) if str(a).strip()]
        data.skill_names.append({"canonical": r.canonical_name, "aliases": aliases})
        data.skill_terms.append(r.canonical_name.lower())
        data.skill_terms.extend(aliases)
    certs = (await session.execute(select(CertScarcity))).scalars().all()
    for c in certs:
        aliases = [str(a).strip().lower() for a in (c.aliases or []) if str(a).strip()]
        data.cert_names.append({"canonical": c.cert_name, "aliases": aliases})
        data.cert_terms.append(c.cert_name.lower())
        data.cert_terms.extend(aliases)
    _ontology_cache = (now, data)
    return data


_NON_WORD = "a-z0-9+#"


def _term_in(text: str, term: str) -> bool:
    """词条匹配：纯拉丁词（如 C/BI/SQL/C++）用词边界，避免 'BI' 误匹配 'RabbitMQ'、
    'C' 误匹配 'CET-6'、'C++' 误算作 'C'；中文词条按子串匹配（'数据'命中'数据库'）。"""
    if term and term.isascii() and all(ch.isalnum() or ch in "+#" for ch in term):
        return re.search(rf"(?<![{_NON_WORD}]){re.escape(term)}(?![{_NON_WORD}])", text) is not None
    return term in text


def _match_terms(text: str, names: list[dict]) -> set[str]:
    """扫描文本，返回命中的规范名集合（别名/大小写不敏感）。"""
    low = (text or "").lower()
    hit: set[str] = set()
    for item in names:
        terms = [item["canonical"].lower(), *item["aliases"]]
        if any(t and _term_in(low, t) for t in terms):
            hit.add(item["canonical"])
    return hit


def scan_skills(text: str, ontology: OntologyData) -> set[str]:
    return _match_terms(text, ontology.skill_names)


def scan_certs(text: str, ontology: OntologyData) -> set[str]:
    return _match_terms(text, ontology.cert_names)


# ---------- 分类树 ----------


async def load_categories(session: AsyncSession) -> CategoryIndex:
    global _categories_cache
    now = time.monotonic()
    if _categories_cache is not None and now - _categories_cache[0] < _CACHE_TTL:
        return _categories_cache[1]
    rows = (await session.execute(select(JdCategory))).scalars().all()
    idx = CategoryIndex()
    for r in rows:
        idx.nodes[r.id] = r
        idx.by_name[r.name] = r
    _categories_cache = (now, idx)
    return idx


_TRACK_KEYWORDS = [
    ("前端", "前端开发"), ("后端", "后端开发"), ("java", "后端开发"), ("c++", "后端开发"),
    ("算法", "算法工程师"), ("机器学习", "算法工程师"), ("深度学习", "算法工程师"),
    ("数据", "数据分析"), ("测试", "测试"), ("运维", "运维"),
    ("产品", "产品经理"), ("用户运营", "用户运营"), ("内容", "内容运营"), ("电商", "电商运营"),
    ("新媒体", "新媒体运营"), ("市场", "市场营销"), ("品牌", "品牌公关"), ("推广", "市场推广"),
    ("人力资源", "人力资源"), ("hr", "人力资源"), ("招聘", "人力资源"),
    ("财务", "财务"), ("会计", "财务"), ("审计", "财务"),
    ("法务", "法务"), ("法律", "法务"), ("行政", "行政"),
]


def _fallback_track(text: str) -> str:
    low = (text or "").lower()
    for kw, track in _TRACK_KEYWORDS:
        if kw in low:
            return track
    return "其他"


def resume_tracks(parsed: dict) -> list[str]:
    """从实习/项目解析结果归一化出赛道列表（LLM 给的 track 优先）。"""
    tracks: list[str] = []
    for it in parsed.get("internships") or []:
        track = (it.get("track") or "").strip()
        ctx = " ".join([str(it.get("company") or ""), str(it.get("position") or "")])
        tracks.append(track if track and track != "其他" else _fallback_track(ctx))
    for p in parsed.get("projects") or []:
        track = (p.get("track") or "").strip()
        if track:
            tracks.append(track if track != "其他" else _fallback_track(str(p.get("name") or "")))
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for t in tracks:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def track_sim(resume_tracks: list[str], jd_leaf_id: uuid.UUID, idx: CategoryIndex) -> float:
    """赛道相似度：同细分 1.0 / 同职能二级 0.7 / 同职能一级 0.5 / 跨职能 0.15 / 无信息 0.4。"""
    if not resume_tracks:
        return 0.4
    leaf = idx.nodes.get(jd_leaf_id)
    if leaf is None:
        return 0.4
    leaf_parent = idx.nodes.get(leaf.parent_id) if leaf.parent_id else None
    best = 0.15
    for t in resume_tracks:
        rc = idx.by_name.get(t)
        if rc is None or rc.id == jd_leaf_id:
            if rc is None:
                continue
            best = max(best, 1.0)
            continue
        if rc.parent_id == leaf.parent_id:
            best = max(best, 0.7)
        else:
            # 同职能一级（level-1 相同、level-2 不同）→ 0.5
            rc_parent = idx.nodes.get(rc.parent_id) if rc.parent_id else None
            if leaf_parent and rc_parent and leaf_parent.parent_id == rc_parent.parent_id:
                best = max(best, 0.5)
    return best


# ---------- 学历 ----------

_EDU_RANK = {"phd": 4, "master": 3, "bachelor": 2, "college": 1}


def _edu_level(s: str | None) -> str | None:
    if not s:
        return None
    if "博士" in s:
        return "phd"
    if "硕士" in s or "研究生" in s:
        return "master"
    if "本科" in s or "学士" in s:
        return "bachelor"
    if "大专" in s:
        return "college"
    return None


def _edu_pass(required: str | None, have: str | None) -> bool | None:
    """None=无法判断（保留）；True=通过；False=未通过。"""
    req = _edu_level(required)
    if not req:
        return None
    if not have:
        return None
    return _EDU_RANK[have] >= _EDU_RANK[req]


# ---------- TF-IDF ----------


def _jd_tokens_cached(jd: JdLibrary, skill_terms: list[str]) -> list[str]:
    """JD 分词结果进程级缓存（按 updated_at 失效，模式同 vector._EMBED_CACHE）。"""
    updated = jd.updated_at.isoformat() if jd.updated_at else ""
    cached = _JD_TOKENS.get(jd.id)
    if cached is not None and cached[0] == updated:
        return cached[1]
    toks = tokenize_with_skills(jd.jd_text or "", skill_terms)
    if len(_JD_TOKENS) > 2000:  # 容量上限，防无限增长
        _JD_TOKENS.clear()
    _JD_TOKENS[jd.id] = (updated, toks)
    return toks


def _cosine(q: Counter, d: Counter, idf: dict[str, float]) -> float:
    qv = {t: q[t] * idf[t] for t in q}
    dv = {t: d[t] * idf[t] for t in d}
    dot = sum(v * dv.get(t, 0) for t, v in qv.items())
    nq = math.sqrt(sum(v * v for v in qv.values()))
    nd = math.sqrt(sum(v * v for v in dv.values()))
    if not nq or not nd:
        return 0.0
    return dot / (nq * nd)


# ---------- 主流程 ----------


def _jd_skills(jd: JdLibrary, ontology: OntologyData) -> list[str]:
    parsed = jd.jd_parsed or {}
    skills = parsed.get("skills") or []
    if skills:
        return [str(s) for s in skills]
    return sorted(scan_skills(jd.jd_text, ontology))


def _jd_certs(jd: JdLibrary, ontology: OntologyData) -> list[str]:
    parsed = jd.jd_parsed or {}
    certs = parsed.get("certs") or []
    if certs:
        return [str(c) for c in certs]
    return sorted(scan_certs(jd.jd_text, ontology))


async def recommend(
    session: AsyncSession,
    parsed: dict,
    resume_text: str,
    top_n: int = 10,
    max_candidates: int = 30,
    reranker=None,
    prefer_city: str | None = None,
) -> list[dict]:
    """返回推荐列表（按 match_score 降序），每项含 jd/hit/missing/reason。

    reranker：可选 VectorReranker（M7.4），可用时对候选做 向量×TF-IDF 混合精排。
    prefer_city：期望工作城市（M7.10）——同城岗位 match_score +6（优先展示），
    异地岗位不排除（应届生可接受异地），reason 标注城市匹配情况。
    """
    ontology = await load_ontology(session)
    idx = await load_categories(session)

    jds = (
        (await session.execute(select(JdLibrary).where(JdLibrary.is_active == True))).scalars().all()  # noqa: E712
    )
    if not jds:
        return []

    # 避雷公司黑名单（M7.11：命中则降权 + 标注）
    from ...models import CompanyWatchlist

    blacklist_rows = (
        (
            await session.execute(
                select(CompanyWatchlist).where(
                    CompanyWatchlist.kind == "blacklist", CompanyWatchlist.status == "active"
                )
            )
        )
        .scalars()
        .all()
    )
    blacklist = {r.company for r in blacklist_rows}

    # 简历侧
    resume_skills = set(str(s) for s in (parsed.get("skills") or []))
    resume_skills |= scan_skills(resume_text, ontology)
    resume_certs = set(str(c) for c in (parsed.get("certs") or []))
    resume_certs |= scan_certs(resume_text, ontology)
    tracks = resume_tracks(parsed)
    basic = parsed.get("basic_info") or {}
    have_edu = _edu_level(str(basic.get("degree") or ""))

    # 硬过滤（学历）
    pool = [jd for jd in jds if _edu_pass(jd.education, have_edu) is not False]
    if not pool:
        return []

    # TF-IDF 粗筛（JD 分词按 updated_at 缓存，避免每请求全库重分词）
    query = resume_text + " " + " ".join(resume_skills)
    doc_toks = [Counter(_jd_tokens_cached(jd, ontology.skill_terms)) for jd in pool]
    q_toks = Counter(tokenize_with_skills(query, ontology.skill_terms))
    df: Counter = Counter()
    for t in doc_toks:
        df.update(t.keys())
    n = len(pool)
    vocab = set(df) | set(q_toks)
    idf = {t: math.log((n + 1) / (df[t] + 1)) + 1 for t in vocab}
    # 向量精排准备（M7.4：可用时对候选做混合相似度）
    query_emb = None
    if reranker is not None and reranker.is_available():
        query_emb = reranker.query_embedding(query)
    scored: list[tuple[float, JdLibrary]] = []
    for i, jd in enumerate(pool):
        sim = _cosine(q_toks, doc_toks[i], idf)
        scored.append((sim, jd))
    scored.sort(key=lambda x: x[0], reverse=True)
    candidates = [jd for _, jd in scored[:max_candidates]]
    sim_map = {jd.id: sim for sim, jd in scored}

    # 精排
    results: list[dict] = []
    for jd in candidates:
        core = _jd_skills(jd, ontology)
        # 大小写不敏感求交：'python' 与 'Python' 视为同一技能，避免 hit/missing 失真
        core_low = {str(s).lower() for s in core}
        res_low = {s.lower() for s in resume_skills}
        hit_low = res_low & core_low
        hit = sorted({s for s in resume_skills if s.lower() in hit_low})
        missing = sorted({s for s in core if s.lower() not in res_low})

        # struct_score
        skill_part = (len(hit) / len(core)) * 50 if core else 25.0
        edu_pass = _edu_pass(jd.education, have_edu)
        edu_part = 100.0 if edu_pass is True else (60.0 if edu_pass is None else 30.0)
        tsim = track_sim(tracks, jd.category_id, idx) if jd.category_id else 0.4
        jd_certs = _jd_certs(jd, ontology)
        if jd_certs:
            cert_part = 100.0 if resume_certs & set(jd_certs) else 30.0
        else:
            cert_part = 60.0
        struct = 0.5 * skill_part + 0.2 * edu_part + 0.2 * tsim * 100 + 0.1 * cert_part

        sim = sim_map[jd.id]
        if query_emb is not None:
            jd_emb = reranker.jd_embedding(
                jd.id, jd.jd_text, jd.updated_at.isoformat() if jd.updated_at else None
            )
            sim = reranker.rerank_similarity(query_emb, jd_emb, sim)

        # 期望城市：同城 +6 优先展示（异地不排除，标注）
        city_match = False
        if prefer_city and jd.city:
            p = prefer_city.strip()
            city_match = p in jd.city or jd.city in p
        city_bonus = 6.0 if city_match else 0.0
        # 避雷公司：降权 -8 并标注
        risk_flag = jd.company in blacklist
        match_score = round(0.6 * struct + 0.4 * sim * 100 + city_bonus + (-8.0 if risk_flag else 0.0), 1)

        results.append(
            {
                "jd": jd,
                "match_score": match_score,
                "hit_skills": hit[:12],
                "missing_skills": missing[:12],
                "edu_pass": edu_pass,
                "track_sim": tsim,
                "sim": sim,
                "struct": struct,
                "city_match": city_match,
                "prefer_city": prefer_city,
                "risk_flag": risk_flag,
            }
        )

    results.sort(key=lambda x: x["match_score"], reverse=True)
    return results[:top_n]


def build_reason(item: dict) -> str:
    parts: list[str] = []
    hit = item["hit_skills"]
    missing = item["missing_skills"]
    if hit:
        parts.append(f"技能命中 {len(hit)} 项（{'、'.join(hit[:5])}）")
    if missing:
        parts.append(f"待补技能：{'、'.join(missing[:5])}")
    edu = item["edu_pass"]
    parts.append("学历符合" if edu is True else ("学历信息待确认" if edu is None else "学历未达要求"))
    tsim = item["track_sim"]
    parts.append("赛道匹配高" if tsim >= 0.7 else ("赛道匹配中" if tsim >= 0.4 else "赛道匹配低"))
    if item.get("prefer_city"):
        jd_city = (item["jd"].city or "").strip()
        if item.get("city_match"):
            parts.append(f"同城岗位（{item['prefer_city']}）")
        elif jd_city:
            parts.append(f"异地岗位（{jd_city}）")
    if item.get("risk_flag"):
        parts.append("⚠️ 该公司有避雷记录，建议核实后慎重投递")
    if item["sim"] >= 0.35:
        parts.append("经历内容相关度高")
    return "；".join(parts)
