"""校招方向模式（docs/07-§17，M7.5）：区分 社招 JD 模式 / 校招方向模式。

校招批次往往没有明确 JD（只有"技术岗/产品岗/管培生"等方向），因此：
- 方向画像（DirectionProfile）：按 jd_category 叶子聚合岗位库 JD 的技能频次，
  叠加 toolchain_template（人工校验）作为"方向核心技能集"；岗位库扩充时自动更新。
- 方向匹配（零 LLM 成本）：简历技能 × 方向核心技能覆盖率 + 赛道对位 + 工具链覆盖。
- 方向级五维报告：把方向画像构造成"伪 JD"，完全复用 evidence 抽取 + 确定性评分。

方向模式评分对象是"方向"而非单条 JD，故不落 Recommendation 表、不接校准反馈
（校准闭环仍面向 JD 模式；后续如需可扩展 direction_feedback 表）。
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import JdCategory, JdLibrary, ToolchainTemplate
from .matching import CategoryIndex, load_categories, track_sim


@dataclass
class DirectionProfile:
    category_id: uuid.UUID
    name: str
    core_skills: list[str] = field(default_factory=list)  # 频次聚合 Top-N（降序）
    toolchain: list[str] = field(default_factory=list)    # 人工校验工具链
    jd_count: int = 0
    text: str = ""

    @property
    def all_skills(self) -> list[str]:
        """方向技能全集（去重保序：工具链优先 + 频次聚合）。"""
        seen: set[str] = set()
        out: list[str] = []
        for s in [*self.toolchain, *self.core_skills]:
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out


async def build_direction_profiles(
    session: AsyncSession, top_skills: int = 12, min_jds: int = 1
) -> list[DirectionProfile]:
    """聚合方向画像：按职能细分叶子分组统计岗位库技能频次。

    只包含有岗位的叶子；技能按出现频次降序取 top_skills。
    """
    idx = await load_categories(session)
    jds = (
        (
            await session.execute(
                select(JdLibrary).where(JdLibrary.is_active == True)  # noqa: E712
            )
        )
        .scalars()
        .all()
    )
    toolchain_rows = (await session.execute(select(ToolchainTemplate))).scalars().all()
    toolchains: dict[uuid.UUID, list[str]] = {
        t.category_id: [str(s) for s in (t.toolchain or [])] for t in toolchain_rows
    }

    from collections import Counter

    freq: dict[uuid.UUID, Counter] = {}
    counts: dict[uuid.UUID, int] = {}
    for jd in jds:
        if not jd.category_id:
            continue
        skills = ((jd.jd_parsed or {}).get("skills") or []) or []
        freq.setdefault(jd.category_id, Counter()).update(str(s) for s in skills)
        counts[jd.category_id] = counts.get(jd.category_id, 0) + 1

    profiles: list[DirectionProfile] = []
    for cat_id, counter in freq.items():
        if counts[cat_id] < min_jds:
            continue
        node = idx.nodes.get(cat_id)
        if node is None:
            continue
        core = [s for s, _ in counter.most_common(top_skills)]
        toolchain = toolchains.get(cat_id, [])
        name = node.name
        text = (
            f"【{name}方向·校招】方向核心技能：{'、'.join(core) or '（岗位库样本不足）'}；"
            f"典型工具链：{'、'.join(toolchain) or '—'}。"
            "该岗位族适合的应届生应具备以上技能与工具链的使用证据（项目/实习）。"
        )
        profiles.append(
            DirectionProfile(
                category_id=cat_id,
                name=name,
                core_skills=core,
                toolchain=toolchain,
                jd_count=counts[cat_id],
                text=text,
            )
        )
    profiles.sort(key=lambda p: -p.jd_count)
    return profiles


# 专业/学科 → 可投方向（就业方向先验，M7.12：方向匹配的加分信号，
# 尤其当简历技能/实习信息较少时，专业是最可靠的方向线索）
MAJOR_DIRECTION_MAP: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"数学|统计|应用数学|精算"), ["数据分析", "算法工程师"]),
    (re.compile(r"计算机|软件|网络工程|信息安全|大数据"), ["后端开发", "前端开发", "算法工程师", "测试"]),
    (re.compile(r"电子|通信|自动化|电气"), ["后端开发", "算法工程师"]),
    (re.compile(r"市场营销|工商管理|国际经济|国际贸易"), ["市场营销", "客户经理助理", "用户运营", "产品经理"]),
    (re.compile(r"经济|金融|保险|投资"), ["客户经理助理", "综合柜员", "运营支持", "财务", "市场营销"]),
    (re.compile(r"会计|财务|审计|税收"), ["财务", "综合柜员"]),
    (re.compile(r"新闻|传播|中文|广告|编辑出版"), ["内容运营", "新媒体运营", "品牌公关"]),
    (re.compile(r"心理"), ["用户运营", "人力资源"]),
    (re.compile(r"人力资源|行政管理"), ["人力资源", "行政"]),
    (re.compile(r"法学|法律"), ["法务"]),
    (re.compile(r"设计|艺术|动画|视觉|美术"), ["前端开发", "内容运营"]),
    (re.compile(r"机械|车辆|工业工程|材料"), ["后端开发", "市场营销"]),
    (re.compile(r"物流|供应链|电子商务"), ["电商运营", "用户运营"]),
    (re.compile(r"教育|师范|汉语国际"), ["内容运营", "人力资源"]),
    (re.compile(r"生物|化学|医药|药学"), ["市场营销", "数据分析"]),
    (re.compile(r"物理|天文"), ["算法工程师", "数据分析"]),
    (re.compile(r"地理|遥感|测绘|环境"), ["数据分析", "前端开发"]),
    (re.compile(r"公共管理|社会学|政治"), ["用户运营", "人力资源", "行政"]),
]


def map_major_to_directions(major: str) -> list[str]:
    """专业名 → 可投方向列表（顺序匹配，命中即取该专业映射）。"""
    if not major:
        return []
    low = major.lower()
    for pattern, dirs in MAJOR_DIRECTION_MAP:
        if pattern.search(low):
            return dirs
    return []


def direction_match_score(
    resume_skills: set[str],
    resume_tracks: list[str],
    profile: DirectionProfile,
    idx: CategoryIndex,
    major_dirs: list[str] | None = None,
    major: str = "",
) -> dict:
    """零 LLM 方向匹配：技能覆盖 50% + 赛道对位 30% + 工具链覆盖 20% + 专业对口加分。

    major_dirs：由专业名映射出的可投方向（M7.12）——命中该方向时 +8 分并标注"专业对口"。

    覆盖率分母补偿（M7.13）：柜员/客服/行政等低门槛方向技能集很窄（<MIN_SKILL_SCOPE），
    命中一两项即接近 100% 覆盖率、分数虚高；分母按下限校准，避免"要求低=分高"失真，
    同时通过 low_barrier 字段供前端标注"该方向门槛较低"。
    """
    MIN_SKILL_SCOPE = 6  # 覆盖率分母下限

    all_skills = profile.all_skills
    hit = sorted(resume_skills & set(all_skills))
    missing = sorted(set(all_skills) - resume_skills)
    raw_scope = len(all_skills)
    low_barrier = 0 < raw_scope < MIN_SKILL_SCOPE
    scope_base = max(raw_scope, MIN_SKILL_SCOPE)
    coverage = len(hit) / scope_base if raw_scope else 0.5

    tsim = track_sim(resume_tracks, profile.category_id, idx)
    if profile.toolchain:
        tool_hit = len(resume_skills & set(profile.toolchain)) / len(profile.toolchain)
    else:
        tool_hit = 0.5

    score = round(0.5 * coverage * 100 + 0.3 * tsim * 100 + 0.2 * tool_hit * 100, 1)

    parts: list[str] = []
    if hit:
        parts.append(f"技能命中 {len(hit)} 项（{'、'.join(hit[:5])}）")
    if missing:
        parts.append(f"待补：{'、'.join(missing[:5])}")
    parts.append("赛道匹配高" if tsim >= 0.7 else ("赛道匹配中" if tsim >= 0.4 else "赛道匹配低"))
    if low_barrier:
        parts.append("该方向技能要求少、门槛较低，命中分偏高不代表竞争小，请结合发展空间与兴趣判断")

    # 专业对口加分（专业是应届生最强方向信号之一）
    major_hit = bool(major_dirs) and profile.name in major_dirs
    if major_hit:
        score = round(score + 8.0, 1)
        parts.append(f"专业对口（{major or '该专业'} 适配此方向）")

    if not hit:
        parts.append("该方向核心技能与简历重合度低，建议补充相关项目")
    return {
        "category_id": profile.category_id,
        "name": profile.name,
        "jd_count": profile.jd_count,
        "score": score,
        "hit_skills": hit[:12],
        "missing_skills": missing[:12],
        "core_skills": profile.core_skills[:12],
        "toolchain": profile.toolchain,
        "skill_scope": raw_scope,
        "low_barrier": low_barrier,
        "reason": "；".join(parts),
    }


def profile_to_pseudo_jd(profile: DirectionProfile, resume_text: str | None = None):
    """把方向画像构造成伪 JD（鸭子类型，供 evidence/scoring 复用）。

    注意：只在方向模式使用，不落 jd_library 表。
    """
    from types import SimpleNamespace

    return SimpleNamespace(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"direction:{profile.category_id}"),
        title=f"{profile.name}方向（校招）",
        company="校招方向画像",
        category_id=profile.category_id,
        industry_id=None,
        education=None,
        jd_text=profile.text,
        jd_parsed={"skills": profile.all_skills, "certs": [], "hard": {}},
        updated_at=None,
    )
