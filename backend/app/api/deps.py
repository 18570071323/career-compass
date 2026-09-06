"""跨路由共享依赖：多租户鉴权（M5）。

实现：HTTP 中间件校验 JWT 并把 tenant_id 写入 contextvar；
路由侧 `ensure_default_tenant` 从 contextvar 取当前租户（公共端点回退默认租户）。
"""
from __future__ import annotations

import contextvars
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Tenant, User

# 中间件写入：当前请求所属租户 ID / 用户 ID
current_tenant_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_tenant_id", default=None
)
current_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_user_id", default=None
)


async def ensure_default_tenant(session: AsyncSession) -> Tenant:
    """返回当前请求的租户（JWT 中间件注入）；公共端点回退默认租户。"""
    ctx = current_tenant_id.get()
    if ctx:
        tenant = await session.get(Tenant, uuid.UUID(ctx))
        if tenant is None or tenant.status != "active":
            raise HTTPException(403, "企业账号不可用")
        return tenant

    # 公共端点（注册/登录/OAuth 回调等）兜底：开发期默认租户
    result = await session.execute(select(Tenant).where(Tenant.name == "默认租户"))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(name="默认租户", plan="enterprise", status="active")
        session.add(tenant)
        await session.flush()
        session.add(
            User(
                tenant_id=tenant.id,
                name="admin",
                email="admin@default.local",
                password_hash="",
                role="admin",
            )
        )
        await session.commit()
        await session.refresh(tenant)
    return tenant
