"""维度评分：与用户 Coze 编程项目 scoreResume（TypeScript）1:1 复刻。

保证产品分数与 demo 完全一致。四维度：经验 40 / 技能 25 / 项目 20 / 亮点 15。
"""
from __future__ import annotations

from typing import Any

from ...schemas import DimensionScore, ScoreResult


def _zero_result(level: str = "无法评估") -> ScoreResult:
    return ScoreResult(
        dimensions={
            "experience_match": DimensionScore(label="经验匹配度", score=0, max=40),
            "skill_match": DimensionScore(label="技能匹配度", score=0, max=25),
            "project_quality": DimensionScore(label="项目质量", score=0, max=20),
            "highlights": DimensionScore(label="综合亮点", score=0, max=15),
        },
        total_score=0,
        max_score=100,
        level=level,  # type: ignore[arg-type]
    )


def compute_scores(parsed: dict[str, Any] | None) -> ScoreResult:
    """复刻 scoreResume：parsed 为简历解析 JSON（缺失字段按空处理）。

    与 TS 一致：解析失败 → 全 0 分 + 等级「无法评估」。
    """
    if parsed is None:
        return _zero_result()

    basic = parsed.get("basic_info") or {}
    work_list = parsed.get("work_experience") or []
    match_points = parsed.get("jd_match_points") or []
    skills = parsed.get("skills") or []
    projects = parsed.get("projects") or []
    highlights = parsed.get("highlights") or []

    # ---------- 维度一：经验匹配度（满分 40） ----------
    score_exp = 0
    years = basic.get("years_of_experience") or 0
    if years >= 5:
        score_exp += 20
    elif years >= 3:
        score_exp += 15
    elif years >= 1:
        score_exp += 10
    else:
        score_exp += 5

    n_work = len(work_list)
    if n_work >= 3:
        score_exp += 10
    elif n_work >= 2:
        score_exp += 7
    elif n_work >= 1:
        score_exp += 4

    n_match = len(match_points)
    if n_match >= 5:
        score_exp += 10
    elif n_match >= 3:
        score_exp += 7
    elif n_match >= 1:
        score_exp += 4

    score_exp = min(score_exp, 40)

    # ---------- 维度二：技能匹配度（满分 25） ----------
    score_skill = 0
    n_skills = len(skills)
    if n_skills >= 10:
        score_skill += 10
    elif n_skills >= 5:
        score_skill += 7
    elif n_skills >= 3:
        score_skill += 4

    match_text = " ".join(str(mp) for mp in match_points).lower()
    # TS：if (skill.toLowerCase() && matchPointsText.includes(skill.toLowerCase()))
    overlap = sum(1 for s in skills if str(s).lower() and str(s).lower() in match_text)
    if overlap >= 5:
        score_skill += 15
    elif overlap >= 3:
        score_skill += 10
    elif overlap >= 1:
        score_skill += 5

    score_skill = min(score_skill, 25)

    # ---------- 维度三：项目质量（满分 20） ----------
    score_project = 0
    n_proj = len(projects)
    if n_proj >= 3:
        score_project += 8
    elif n_proj >= 2:
        score_project += 6
    elif n_proj >= 1:
        score_project += 3

    detailed = sum(
        1
        for p in projects
        if (p.get("contribution") or "") and len(str(p.get("contribution"))) > 10
    )
    if detailed >= 3:
        score_project += 12
    elif detailed >= 2:
        score_project += 8
    elif detailed >= 1:
        score_project += 4

    score_project = min(score_project, 20)

    # ---------- 维度四：综合亮点（满分 15） ----------
    score_highlight = 0
    n_hl = len(highlights)
    if n_hl >= 3:
        score_highlight += 10
    elif n_hl >= 2:
        score_highlight += 7
    elif n_hl >= 1:
        score_highlight += 4

    education = str(basic.get("education") or "").lower()
    if "博士" in education or "phd" in education:
        score_highlight += 5
    elif "硕士" in education or "master" in education:
        score_highlight += 4
    elif "本科" in education or "bachelor" in education or "学士" in education:
        score_highlight += 2

    score_highlight = min(score_highlight, 15)

    # ---------- 汇总 ----------
    total = score_exp + score_skill + score_project + score_highlight
    if total >= 80:
        level = "强烈推荐"
    elif total >= 60:
        level = "推荐"
    elif total >= 40:
        level = "待定"
    else:
        level = "不推荐"

    return ScoreResult(
        dimensions={
            "experience_match": DimensionScore(label="经验匹配度", score=score_exp, max=40),
            "skill_match": DimensionScore(label="技能匹配度", score=score_skill, max=25),
            "project_quality": DimensionScore(label="项目质量", score=score_project, max=20),
            "highlights": DimensionScore(label="综合亮点", score=score_highlight, max=15),
        },
        total_score=total,
        max_score=100,
        level=level,  # type: ignore[arg-type]
    )
