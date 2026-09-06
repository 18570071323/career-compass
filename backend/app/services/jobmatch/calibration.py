"""校准闭环服务（docs/07-§8，M7.3）。

- 配置：CalibrationConfig 表（阈值/证书稀缺度覆盖/信号词/档位权重覆盖），评分引擎启动时读取
- 统计：周度维度偏差率（按维度/档位/岗位类别分组）、校准 MAE、反馈明细
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import CalibrationConfig, CalibrationFeedback, JdCategory, JdLibrary
from .scoring import DIM_LABELS, TIER_LABELS, WEIGHT_TIERS

DEFAULT_CONFIG: dict[str, Any] = {
    "level_thresholds": {"S": 85, "A": 70, "B": 55},
    "cert_scarcity": {},  # {证书规范名: 1-5} 覆盖默认表
    "signal_words": {"industry_cognition": ["行业报告", "竞品分析", "市场调研", "用户洞察", "政策解读", "赛道研究"]},
    "tier_weights": {},  # {档位: {维度: 权重}} 覆盖默认三档
}

DIMENSIONS = list(DIM_LABELS.keys())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def ensure_config_defaults(session: AsyncSession) -> None:
    """幂等写入默认配置。"""
    for key, value in DEFAULT_CONFIG.items():
        exists = await session.scalar(select(CalibrationConfig).where(CalibrationConfig.key == key))
        if exists is None:
            session.add(CalibrationConfig(key=key, value=value))
    await session.commit()


async def get_config(session: AsyncSession) -> dict[str, Any]:
    """读取全部校准配置（合并默认值）。"""
    await ensure_config_defaults(session)
    cfg = {k: (v.copy() if isinstance(v, dict) else v) for k, v in DEFAULT_CONFIG.items()}
    rows = (await session.execute(select(CalibrationConfig))).scalars().all()
    for r in rows:
        if isinstance(r.value, dict):
            target = cfg.get(r.key)
            if isinstance(target, dict):
                target.update(r.value)
            else:
                cfg[r.key] = r.value
    return cfg


async def update_config(session: AsyncSession, key: str, value: dict) -> dict:
    """更新一个配置键（整值替换）。"""
    await ensure_config_defaults(session)
    row = await session.scalar(select(CalibrationConfig).where(CalibrationConfig.key == key))
    if row is None:
        row = CalibrationConfig(key=key, value=value)
        session.add(row)
    else:
        row.value = value
    await session.commit()
    return value


async def record_feedback(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    role: str,
    target_type: str,
    analysis_id: uuid.UUID | None,
    resume_id: uuid.UUID | None,
    jd_id: uuid.UUID | None,
    model_total: float | None,
    dim_overrated: list[str],
    dim_underrated: list[str],
    dim_ok: list[str],
    agree_interview: bool | None,
    suggested_score: float | None,
    comment: str | None,
) -> CalibrationFeedback:
    row = CalibrationFeedback(
        tenant_id=tenant_id,
        user_id=user_id,
        role=role if role in ("hr", "candidate") else "candidate",
        target_type=target_type,
        analysis_id=analysis_id,
        resume_id=resume_id,
        jd_id=jd_id,
        model_total=model_total,
        dim_overrated=dim_overrated or [],
        dim_underrated=dim_underrated or [],
        dim_ok=dim_ok or [],
        agree_interview=agree_interview,
        suggested_score=suggested_score,
        comment=comment,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def compute_stats(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    days: int = 7,
    role: str | None = None,
    group_by: str = "none",
) -> dict[str, Any]:
    """校准统计：维度偏差率（全局或按档位/岗位类别分组）+ 校准 MAE + 近期反馈。

    必须传入 tenant_id：统计与明细严格限定在当前租户内，防止跨租户泄露反馈数据。
    """
    since = _now() - timedelta(days=max(1, days))
    conds = [
        CalibrationFeedback.created_at >= since,
        CalibrationFeedback.tenant_id == tenant_id,
    ]
    if role in ("hr", "candidate"):
        conds.append(CalibrationFeedback.role == role)

    rows = (
        (
            await session.execute(
                select(CalibrationFeedback).where(*conds).order_by(CalibrationFeedback.created_at.desc()).limit(200)
            )
        )
        .scalars()
        .all()
    )
    n_total = len(rows)
    n_hr = sum(1 for r in rows if r.role == "hr")

    # 维度偏差率（全局）
    dim_stats: dict[str, dict[str, int | float]] = {}
    for dim in DIMENSIONS:
        over = sum(1 for r in rows if dim in (r.dim_overrated or []))
        under = sum(1 for r in rows if dim in (r.dim_underrated or []))
        ok = sum(1 for r in rows if dim in (r.dim_ok or []))
        judged = over + under + ok
        dim_stats[dim] = {
            "label": DIM_LABELS[dim],
            "over": over,
            "under": under,
            "ok": ok,
            "judged": judged,
            "over_rate": round(over / judged, 3) if judged else 0.0,
            "under_rate": round(under / judged, 3) if judged else 0.0,
        }

    # 校准 MAE（有 suggested_score 的行）
    with_score = [r for r in rows if r.suggested_score is not None and r.model_total is not None]
    mae = (
        round(sum(abs(r.model_total - r.suggested_score) for r in with_score) / len(with_score), 2)
        if with_score
        else None
    )
    mae_samples = len(with_score)

    # 分组偏差率（按档位 / 岗位类别）
    groups: dict[str, dict] = {}
    if group_by in ("tier", "category"):
        for r in rows:
            key = ""
            if group_by == "tier":
                # 从关联 recommendation.score_result.tier 取（jd_id 关联行）；无则 unknown
                key = r.target_type  # 占位，下面用映射
            # 简化实现：按 jd 关联的推荐记录 tier 或岗位类别名
        # 重新计算：需要 recommendation 关联
        from ...models import Recommendation

        reco_map: dict[uuid.UUID, dict] = {}
        recos = (
            (
                await session.execute(
                    select(Recommendation).where(
                        Recommendation.jd_id.in_([r.jd_id for r in rows if r.jd_id])
                    )
                )
            )
            .scalars()
            .all()
        )
        for rec in recos:
            reco_map[rec.jd_id] = rec
        cat_names = {}
        cat_rows = (await session.execute(select(JdCategory))).scalars().all()
        for c in cat_rows:
            cat_names[c.id] = c.name
        jd_cat: dict[uuid.UUID, uuid.UUID | None] = {}
        jd_rows = (
            (
                await session.execute(
                    select(JdLibrary).where(JdLibrary.id.in_([r.jd_id for r in rows if r.jd_id]))
                )
            )
            .scalars()
            .all()
        )
        for jd in jd_rows:
            jd_cat[jd.id] = jd.category_id
        for r in rows:
            rec = reco_map.get(r.jd_id)
            if group_by == "tier":
                key = (rec.score_result or {}).get("tier", "unknown") if rec else "unknown"
            else:
                cat_id = jd_cat.get(r.jd_id) if r.jd_id else None
                key = cat_names.get(cat_id, "未知") if cat_id else "未知"
            g = groups.setdefault(
                key, {"key": key, "over": 0, "under": 0, "ok": 0, "n": 0}
            )
            g["n"] += 1
            for dim in r.dim_overrated or []:
                g["over"] += 1
            for dim in r.dim_underrated or []:
                g["under"] += 1
            for dim in r.dim_ok or []:
                g["ok"] += 1
        for g in groups.values():
            total_marks = g["over"] + g["under"] + g["ok"]
            g["over_rate"] = round(g["over"] / total_marks, 3) if total_marks else 0.0
            g["under_rate"] = round(g["under"] / total_marks, 3) if total_marks else 0.0
        groups = dict(sorted(groups.items(), key=lambda kv: -kv[1]["n"]))

    recent = [
        {
            "id": str(r.id),
            "role": r.role,
            "target_type": r.target_type,
            "model_total": r.model_total,
            "suggested_score": r.suggested_score,
            "agree_interview": r.agree_interview,
            "over": r.dim_overrated or [],
            "under": r.dim_underrated or [],
            "ok": r.dim_ok or [],
            "comment": r.comment,
            "created_at": _aware(r.created_at).isoformat() if r.created_at else None,
        }
        for r in rows[:50]
    ]

    return {
        "period_days": days,
        "total": n_total,
        "hr_count": n_hr,
        "candidate_count": n_total - n_hr,
        "dimensions": dim_stats,
        "mae": mae,
        "mae_samples": mae_samples,
        "groups": groups if group_by in ("tier", "category") else {},
        "recent": recent,
        "tiers": TIER_LABELS,
    }
