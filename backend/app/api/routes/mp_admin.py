"""C 端小程序管理后台（次数包发放 / 免费额度重置 / 流水对账）。

入口：Web 控制台「小程序用户」页，仅企业管理员（User.role == 'admin'）可操作。
阶段一支付（个人主体受限）：客服线下收款 → 管理员在此按 openid 给用户发放次数包。
说明：当前为个人/单主体运营，管理员可对全局 mp_user 操作；后续多主体分销可再加范围限制。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_session
from ...models import MpQuotaLog, MpUser, User
from ..deps import current_user_id

router = APIRouter(prefix="/api/v1/admin/mp", tags=["mp-admin"])


class GrantIn(BaseModel):
    user_id: uuid.UUID
    delta: int = Field(default=5, ge=1, le=999, description="发放次数（正数）")
    reason: str = Field(default="线下转账开通", max_length=120)


class ResetIn(BaseModel):
    user_id: uuid.UUID


async def _require_admin(session: AsyncSession) -> User:
    uid = current_user_id.get()
    user = await session.get(User, uuid.UUID(uid)) if uid else None
    if user is None or user.role != "admin":
        raise HTTPException(403, "仅企业管理员可操作")
    return user


def _free_left(u: MpUser) -> int:
    return 0 if (u.direction_free_used or u.job_free_used or u.guide_free_used) else 1


def _user_dict(u: MpUser) -> dict:
    return {
        "user_id": str(u.id),
        "openid": u.openid,
        "nickname": u.nickname,
        "free_left": _free_left(u),
        "pack_quota": u.pack_quota,
        "has_resume": bool(u.last_resume_text),
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@router.get("/users")
async def list_users(
    q: str = Query("", max_length=64),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """按 openid / 昵称模糊搜索 C 端用户；q 为空则返回最近创建的。"""
    await _require_admin(session)
    stmt = select(MpUser).order_by(MpUser.created_at.desc()).limit(limit)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = (
            select(MpUser)
            .where(or_(MpUser.openid.like(like), MpUser.nickname.like(like)))
            .order_by(MpUser.created_at.desc())
            .limit(limit)
        )
    rows = (await session.execute(stmt)).scalars().all()
    return {"items": [_user_dict(u) for u in rows], "total": len(rows)}


@router.post("/grant")
async def grant_quota(
    payload: GrantIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """给用户发放次数包（客服收款后操作），并记录流水。"""
    admin = await _require_admin(session)
    user = await session.get(MpUser, payload.user_id)
    if user is None:
        raise HTTPException(404, "用户不存在")
    before = user.pack_quota
    user.pack_quota = before + payload.delta
    session.add(
        MpQuotaLog(
            mp_user_id=user.id,
            openid=user.openid,
            delta=payload.delta,
            balance_after=user.pack_quota,
            reason=payload.reason or "线下转账开通",
            operator_id=admin.id,
        )
    )
    await session.commit()
    return {"ok": True, "user": _user_dict(user), "delta": payload.delta}


@router.post("/reset-free")
async def reset_free(
    payload: ResetIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """重置该用户的免费体验总池（三个功能标记清空，可再获 1 次免费）。"""
    await _require_admin(session)
    user = await session.get(MpUser, payload.user_id)
    if user is None:
        raise HTTPException(404, "用户不存在")
    user.direction_free_used = False
    user.job_free_used = False
    user.guide_free_used = False
    await session.commit()
    return {"ok": True, "user": _user_dict(user)}


@router.get("/logs")
async def quota_logs(
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """最近发放/调整流水（对账用）。"""
    await _require_admin(session)
    rows = (
        (
            await session.execute(
                select(MpQuotaLog).order_by(MpQuotaLog.created_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": str(r.id),
                "openid": r.openid,
                "delta": r.delta,
                "balance_after": r.balance_after,
                "reason": r.reason,
                "operator_id": str(r.operator_id) if r.operator_id else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }
