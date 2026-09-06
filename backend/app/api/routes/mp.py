"""求职端小程序「简历罗盘」API（C 端）。

账号：POST /login、GET /me、GET /packs
能力（均含免费/次数包扣次）：
  POST /direction-match   职业方向匹配（简历文件 + 可选偏好）
  POST /match-report      岗位匹配报告 + 简历优化建议（简历文件 + 目标岗位 JD）
  POST /guide             求职导航（个性化信息 → 路线图）
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...db import get_session
from ...models import MpUser
from ...schemas import MpGuideRequest, MpLoginRequest
from ...services.auth import create_mp_token, decode_token
from ...services.engine.doc_extract import DocExtractError, extract_text
from ...services.engine.llm import DeepSeekClient, LLMError
from ...services.engine.scoring import compute_scores

router = APIRouter(prefix="/api/v1/mp", tags=["mp"])

_bearer = HTTPBearer(auto_error=False)

# 开发期自动补给次数包的额度底线（仅 dev_ 测试号；正式 wx_secret 模式不使用）
DEV_PACK_FLOOR = 50

MAX_FILE = 20 * 1024 * 1024
ALLOWED = {".pdf", ".doc", ".docx", ".txt"}


async def _get_mp_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> MpUser:
    if creds is None or not creds.credentials:
        raise HTTPException(401, "请先登录小程序")
    try:
        payload = decode_token(creds.credentials)
        if payload.get("kind") != "mp":
            raise ValueError("wrong token kind")
        openid = payload["sub"]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(401, "登录已过期，请重新进入小程序") from exc
    user = await session.scalar(select(MpUser).where(MpUser.openid == openid))
    if user is None:
        raise HTTPException(401, "用户不存在，请重新登录")
    return user


def _llm() -> DeepSeekClient:
    settings = get_settings()
    if not settings.llm_configured:
        raise HTTPException(503, "AI 引擎未配置，请联系客服")
    return DeepSeekClient(settings)


def _free_used(user: MpUser) -> bool:
    """任一功能用过免费即视为已用（免费总池 = 1 次，三功能任选其一）。"""
    return user.direction_free_used or user.job_free_used or user.guide_free_used


def _spend(user: MpUser) -> str:
    """优先扣唯一免费额度，其次扣次数包；都没有 → 402。"""
    if not _free_used(user):
        # 一次性把三个标记置位，表示免费总池已消耗
        user.direction_free_used = True
        user.job_free_used = True
        user.guide_free_used = True
        return "free"
    if user.pack_quota > 0:
        user.pack_quota -= 1
        return "pack"
    raise HTTPException(402, "免费体验已用完，请购买次数包后继续")


# 方向匹配捆绑体验的成本上限（防止单次次数包触发大量 LLM 调用）：
# 每方向每动作（报告/优化）在一次匹配内只生成 1 次；整场匹配免费深度报告合计 ≤ 10 次。
BUNDLE_PER_DIR = 1
BUNDLE_MAX_TOTAL = 10


def _bundle_consume(user: MpUser, match_session: str | None, direction_key: str, action: str, action_label: str) -> str:
    """方向报告 / 按方向优化的捆绑扣次：
    - 携带本次「方向匹配」的 session → 捆绑免费，但受成本上限约束（每方向每动作 1 次、全场 ≤10 次）；
    - 无有效 session → 走原按次收费（免费池/次数包）。"""
    if not (match_session and user.last_dir_session and match_session == user.last_dir_session):
        return _spend(user)
    usage: dict = dict(user.last_dir_usage or {})
    sub: dict = dict(usage.get(direction_key) or {})
    total = sum(int(x) for v in usage.values() for x in dict(v).values())
    if int(sub.get(action, 0)) >= BUNDLE_PER_DIR:
        raise HTTPException(429, f"{action_label}已在该方向生成过一次（本次匹配内不重复生成），请更换方向或重新做「方向匹配」")
    if total >= BUNDLE_MAX_TOTAL:
        raise HTTPException(429, f"本次方向匹配的免费深度分析已达上限（{BUNDLE_MAX_TOTAL} 次），如需更多请重新做「方向匹配」")
    sub[action] = int(sub.get(action, 0)) + 1
    usage[direction_key] = sub
    user.last_dir_usage = usage
    return "bundle"


async def _read_resume(file: UploadFile, content: bytes) -> str:
    if not file.filename:
        raise HTTPException(400, "缺少简历文件")
    suffix = "." + file.filename.lower().rsplit(".", 1)[-1]
    if suffix not in ALLOWED:
        raise HTTPException(400, f"不支持的简历格式：{suffix}")
    if len(content) > MAX_FILE:
        raise HTTPException(400, "简历文件超过 20MB")
    try:
        text = extract_text(file.filename, content)
    except DocExtractError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not text.strip():
        raise HTTPException(400, "未能从简历提取到文本")
    return text


async def _code_to_openid(code: str) -> str:
    settings = get_settings()
    if settings.wx_secret:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://api.weixin.qq.com/sns/jscode2session",
                    params={
                        "appid": settings.wx_appid,
                        "secret": settings.wx_secret,
                        "js_code": code,
                        "grant_type": "authorization_code",
                    },
                )
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"微信登录服务不可用：{exc}") from exc
        if "openid" not in data:
            raise HTTPException(400, f"微信登录失败：{data.get('errmsg', data)}")
        return data["openid"]
    return "dev_" + code[:32] if not code.startswith("dev_") else code


# ---------- 账号 ----------


@router.post("/login")
async def login(payload: MpLoginRequest, session: AsyncSession = Depends(get_session)) -> dict:
    openid = await _code_to_openid(payload.code)
    user = await session.scalar(select(MpUser).where(MpUser.openid == openid))
    if user is None:
        user = MpUser(openid=openid, nickname=payload.nickname)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    # 开发自动补次数包：仅当未配 wx_secret（dev_ 测试号）+ DEBUG 时生效，
    # 便于验收时畅测各功能；正式版（配置 wx_secret）不受影响，付费墙逻辑不变。
    settings = get_settings()
    if settings.debug and not settings.wx_secret and str(openid).startswith("dev_") and user.pack_quota < DEV_PACK_FLOOR:
        user.pack_quota = DEV_PACK_FLOOR
        await session.commit()
    return {"token": create_mp_token(openid), "openid": openid}


def _user_payload(u: MpUser) -> dict:
    free_left = 0 if _free_used(u) else 1
    return {
        "user_id": str(u.id),
        "openid": u.openid,
        "nickname": u.nickname,
        "quota": {
            "free_left": free_left,  # 总免费池（三功能任选其一，共 1 次）
            "pack_quota": u.pack_quota,
        },
    }


@router.get("/me")
async def me(
    user: MpUser = Depends(_get_mp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    fresh = await session.scalar(select(MpUser).where(MpUser.id == user.id))
    return _user_payload(fresh)


@router.get("/packs")
async def packs() -> dict:
    settings = get_settings()
    items = [
        {"pack": k, "count": v["count"], "price": v["price"]}
        for k, v in settings.mp_pack_pricing.items()
    ]
    return {"items": items}


# ---------- 分析能力 ----------


@router.post("/direction-match")
async def direction_match(
    file: UploadFile = File(...),
    top_n: int = Form(6),
    user: MpUser = Depends(_get_mp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """职业方向匹配（与网站一致）：岗位库方向画像确定性打分（分数/命中缺失技能/理由）。"""
    content = await file.read()
    text = await _read_resume(file, content)
    settings = get_settings()
    from ...services.jobmatch.seed import ensure_seeded
    from ...services.jobmatch.parse import parse_graduate
    from ...services.jobmatch.matching import load_categories, load_ontology, resume_tracks, scan_skills
    from ...services.jobmatch.direction import (
        build_direction_profiles,
        direction_match_score,
        map_major_to_directions,
    )

    await ensure_seeded(session)
    warnings: list[str] = []
    parsed: dict = {}
    llm = DeepSeekClient(settings) if settings.llm_configured else None
    try:
        if llm is not None:
            parsed = await parse_graduate(llm, text)
        else:
            warnings.append("未配置 AI Key，匹配精度受限")
    finally:
        if llm is not None:
            await llm.aclose()

    ontology = await load_ontology(session)
    resume_skills = set(str(s) for s in (parsed.get("skills") or [])) | scan_skills(text, ontology)
    tracks = resume_tracks(parsed)
    idx = await load_categories(session)
    basic = parsed.get("basic_info") or {}
    major = str(basic.get("major") or "")
    major_dirs = map_major_to_directions(major)

    profiles = await build_direction_profiles(session)
    scored = [
        direction_match_score(resume_skills, tracks, p, idx, major_dirs=major_dirs, major=major)
        for p in profiles
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    top_n = max(1, min(top_n, 20))
    items = [
        {
            "rank": i,
            "score": round(float(s.get("score", 0)), 1),
            "category_id": str(s["category_id"]),
            "name": s.get("name", ""),
            "jd_count": s.get("jd_count", 0),
            "hit_skills": s.get("hit_skills", []),
            "missing_skills": s.get("missing_skills", []),
            "core_skills": s.get("core_skills", []),
            "toolchain": s.get("toolchain", []),
            "reason": s.get("reason", ""),
            "skill_scope": s.get("skill_scope"),
            "low_barrier": s.get("low_barrier"),
        }
        for i, s in enumerate(scored[:top_n], start=1)
    ]

    spent = _spend(user)
    match_session = str(uuid.uuid4())
    user.last_resume_text = text
    user.last_resume_parsed = parsed or None
    user.last_dir_session = match_session
    user.last_dir_usage = {}  # 新会话重置捆绑用量统计
    await session.commit()
    fresh = await session.scalar(select(MpUser).where(MpUser.id == user.id))
    return {
        "items": items,
        "total": len(items),
        "resume_name": basic.get("name"),
        "session": match_session,  # 报告/按方向优化携带此值则不重复扣次
        "warnings": warnings,
        "spent": spent,
        "quota": _user_payload(fresh)["quota"],
    }


@router.post("/direction-report")
async def direction_report(
    category_id: uuid.UUID = Form(...),
    match_session: str | None = Form(None, alias="session"),
    user: MpUser = Depends(_get_mp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """方向级五维报告（无 JD）：复用最近一次方向匹配的简历，以方向画像为伪 JD。
    携带方向匹配返回的 session 时不重复扣次（捆绑体验）。"""
    parsed = user.last_resume_parsed or {}
    parsed_text = user.last_resume_text or ""
    if not parsed_text:
        raise HTTPException(400, "请先做「方向匹配」上传简历，再查看方向报告")

    settings = get_settings()
    from ...services.jobmatch.calibration import get_config
    from ...services.jobmatch.direction import build_direction_profiles, profile_to_pseudo_jd
    from ...services.jobmatch.evidence import extract_evidence, fallback_evidence
    from ...services.jobmatch.report import generate_five_dim_report, template_report
    from ...services.jobmatch.scoring import compute_five_dim_scores, suggest_tier
    from ...services.jobmatch.seed import ensure_seeded

    await ensure_seeded(session)
    profiles = await build_direction_profiles(session)
    profile = next((p for p in profiles if p.category_id == category_id), None)
    if profile is None:
        raise HTTPException(404, "方向不存在或岗位库暂无该方向样本")

    warnings: list[str] = []
    llm = DeepSeekClient(settings) if settings.llm_configured else None
    evidence: dict = {}
    try:
        if llm is not None:
            jd_info = {
                "title": f"{profile.name}方向（校招）",
                "company": "校招方向画像",
                "category": profile.name,
                "industry": None,
                "jd_text": profile.text,
                "jd_skills": profile.all_skills,
            }
            evidence = await extract_evidence(llm, parsed, jd_info)
        else:
            warnings.append("未配置 AI Key，采用本地证据（精度受限）")
        if not evidence:
            evidence = fallback_evidence(parsed, parsed_text)

        cfg = await get_config(session)
        tier = suggest_tier(f"{profile.name}方向", None)
        pseudo = profile_to_pseudo_jd(profile)
        score = await compute_five_dim_scores(session, parsed, parsed_text, evidence, pseudo, tier, cfg=cfg)
        if llm is not None:
            report_md = await generate_five_dim_report(llm, parsed, evidence, score, pseudo.title, pseudo.jd_text)
        else:
            report_md = template_report(parsed, evidence, score, pseudo.title)
    finally:
        if llm is not None:
            await llm.aclose()

    spent = _bundle_consume(user, match_session, str(category_id), "report", "方向报告")
    await session.commit()
    fresh = await session.scalar(select(MpUser).where(MpUser.id == user.id))
    return {
        "target": profile.name,
        "category_id": str(profile.category_id),
        "score": {
            "dimensions": {k: dict(v) for k, v in score["dimensions"].items()},
            "total_score": score["total_score"],
            "max_score": score["max_score"],
            "level": score["level"],
            "tier": score["tier"],
            "tier_label": score["tier_label"],
            "doubts": score["doubts"],
            "hit_skills": score["hit_skills"],
            "missing_skills": score["missing_skills"],
        },
        "report_md": report_md,
        "warnings": warnings,
        "spent": spent,  # "bundle"=包含在方向匹配额度内 | "free"/"pack"=本次单独扣次
        "quota": _user_payload(fresh)["quota"],
    }


@router.post("/direction-optimize")
async def direction_optimize(
    category_id: uuid.UUID | None = Form(None),
    match_session: str | None = Form(None, alias="session"),
    user: MpUser = Depends(_get_mp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """简历针对性优化建议：按方向画像优化（复用网站 resume_analyze），可指定方向，留空为通用。
    携带方向匹配返回的 session 时不重复扣次（捆绑体验）。"""
    parsed = user.last_resume_parsed or {}
    parsed_text = user.last_resume_text or ""
    if not parsed_text:
        raise HTTPException(400, "请先做「方向匹配」上传简历，再查看优化建议")

    settings = get_settings()
    from ...services.jobmatch.resume_analyze import analyze_resume, fallback_analysis
    from ...services.jobmatch.seed import ensure_seeded

    target = ""
    if category_id is not None:
        from ...services.jobmatch.direction import build_direction_profiles

        await ensure_seeded(session)
        profiles = await build_direction_profiles(session)
        profile = next((p for p in profiles if p.category_id == category_id), None)
        if profile is not None:
            target = (
                f"目标方向：{profile.name}（岗位库 {profile.jd_count} 条样本）\n"
                f"方向核心技能：{'、'.join(profile.core_skills) or '（样本不足）'}\n"
                f"典型工具链：{'、'.join(profile.toolchain) or '—'}"
            )

    warnings: list[str] = []
    llm = DeepSeekClient(settings) if settings.llm_configured else None
    analysis: dict = {}
    try:
        if llm is not None:
            analysis = await analyze_resume(llm, parsed, parsed_text, target=target)
        else:
            warnings.append("未配置 AI Key，采用规则兜底分析")
            analysis = fallback_analysis(parsed)
    finally:
        if llm is not None:
            await llm.aclose()

    key = str(category_id) if category_id is not None else "general"
    spent = _bundle_consume(user, match_session, key, "optimize", "简历优化建议")
    await session.commit()
    fresh = await session.scalar(select(MpUser).where(MpUser.id == user.id))
    return {
        "target": target or None,
        "analysis": analysis,
        "warnings": warnings,
        "spent": spent,  # "bundle"=包含在方向匹配额度内 | "free"/"pack"=本次单独扣次
        "quota": _user_payload(fresh)["quota"],
    }



@router.post("/match-report")
async def match_report(
    file: UploadFile = File(...),
    jd_text: str = Form(..., min_length=10),
    user: MpUser = Depends(_get_mp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """岗位匹配报告 + 简历优化建议：免费体验 1 个岗位，之后扣次数包。分析成功才扣次。"""
    content = await file.read()
    text = await _read_resume(file, content)
    llm = _llm()
    try:
        parsed = await llm.parse_resume(text, jd_text)
        score = compute_scores(parsed)
        score_json = score.model_dump(mode="json")
        report_md = await llm.generate_report(parsed, score_json, jd_text, lang="zh")
        advice = await llm.resume_advice(parsed, score_json, jd_text)
    except LLMError as exc:
        raise HTTPException(502, f"分析失败：{exc}") from exc

    spent = _spend(user)
    await session.commit()
    fresh = await session.scalar(select(MpUser).where(MpUser.id == user.id))
    return {
        "score_result": score_json,
        "report_md": report_md,
        "optimization": advice,
        "spent": spent,
        "quota": _user_payload(fresh)["quota"],
    }


@router.post("/guide")
async def guide(
    payload: MpGuideRequest,
    user: MpUser = Depends(_get_mp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """求职导航：免费 1 次，之后扣次数包。分析成功才扣次。"""
    try:
        result = await _llm().job_guide(payload.model_dump())
    except LLMError as exc:
        raise HTTPException(502, f"分析失败：{exc}") from exc
    spent = _spend(user)
    await session.commit()
    fresh = await session.scalar(select(MpUser).where(MpUser.id == user.id))
    return {"result": result, "spent": spent, "quota": _user_payload(fresh)["quota"]}


# ============ 求职导航（与网站 CareerPlan 问卷对齐，docs/07-M7.15） ============


@router.get("/career-directions")
async def career_directions(session: AsyncSession = Depends(get_session)) -> dict:
    """可选的求职导航目标方向（岗位库方向画像名，与网站一致）。"""
    from ...services.jobmatch.direction import build_direction_profiles
    from ...services.jobmatch.seed import ensure_seeded

    await ensure_seeded(session)
    profiles = await build_direction_profiles(session)
    items = [
        {"name": p.name, "jd_count": p.jd_count, "category_id": str(p.category_id)}
        for p in profiles
    ]
    return {"items": items}


@router.get("/direction-profile")
async def direction_profile_meta(
    name: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """目标方向画像（核心技能/工具链，供问卷勾选已会技能）。"""
    from ...services.jobmatch.career_plan import find_direction_profile
    from ...services.jobmatch.seed import ensure_seeded

    await ensure_seeded(session)
    p = await find_direction_profile(session, name.strip())
    if p is None:
        return {"name": name, "found": False, "core_skills": [], "toolchain": [], "jd_count": 0}
    return {
        "name": p.name,
        "found": True,
        "core_skills": p.core_skills[:12],
        "toolchain": p.toolchain,
        "jd_count": p.jd_count,
    }


@router.post("/career-plan")
async def career_plan(
    payload: dict,
    user: MpUser = Depends(_get_mp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """求职导航（职业规划问卷）：复用网站 career_plan 引擎，免费 1 次，成功才扣次。"""
    from ...services.jobmatch.career_plan import compute_career_plan
    from ...services.jobmatch.seed import ensure_seeded

    settings = get_settings()
    await ensure_seeded(session)
    llm = DeepSeekClient(settings) if settings.llm_configured else None
    try:
        result = await compute_career_plan(session, dict(payload), llm=llm)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"规划生成失败：{exc}") from exc
    finally:
        if llm is not None:
            await llm.aclose()
    if result.get("error"):
        raise HTTPException(400, result["error"])

    spent = _spend(user)
    await session.commit()
    fresh = await session.scalar(select(MpUser).where(MpUser.id == user.id))
    return {"result": result, "spent": spent, "quota": _user_payload(fresh)["quota"]}
