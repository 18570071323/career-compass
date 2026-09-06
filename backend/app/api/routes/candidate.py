"""C 端应届生求职 API（docs/07，M7.1）。

- POST /api/v1/candidate/recommend  上传简历 → 推荐 Top-N 岗位（含命中/缺失技能、理由）
- GET  /api/v1/candidate/jd-library  岗位库浏览/搜索
- GET  /api/v1/candidate/categories  分类树（行业 + 职能）
- GET  /api/v1/candidate/jd/{id}     岗位详情

说明：岗位库为空时自动灌入种子数据（docs/07-§4，人工精选 70 条）。
配额：M7.1 推荐不消耗分析配额（配额接入随 M7.3 校准闭环一起落地）。
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...db import get_session
from ...models import CompanyWatchlist, JdCategory, JdLibrary, Recommendation, Resume
from ...schemas import (
    CategoryNode,
    CompanyIn,
    CompanyItem,
    CrawlIn,
    CrawlOut,
    DimensionDetail,
    DirectionItem,
    DirectionMatchOut,
    FiveDimScore,
    JdLibraryDetail,
    JdLibraryItem,
    RecommendOut,
    RecommendationItem,
    ResumeAnalysisOut,
    ResumeRewriteOut,
    ScoreOut,
)
from ...services.engine.doc_extract import DocExtractError, extract_text
from ...services.engine.llm import DeepSeekClient
from ...services.jobmatch.direction import (
    build_direction_profiles,
    direction_match_score,
    profile_to_pseudo_jd,
)
from ...services.jobmatch.evidence import extract_evidence, fallback_evidence
from ...services.jobmatch.matching import (
    build_reason,
    load_categories,
    load_ontology,
    recommend,
    resume_tracks,
    scan_skills,
)
from ...services.jobmatch.parse import parse_graduate
from ...services.jobmatch.report import generate_five_dim_report
from ...services.jobmatch.scoring import compute_five_dim_scores, suggest_tier
from ...services.jobmatch.seed import ensure_seeded
from ...services.storage import ALLOWED_SUFFIX, MAX_FILE_SIZE, save_resume_file
from ..deps import ensure_default_tenant

logger = logging.getLogger(__name__)


def _safe_http_url(url: str) -> str:
    """投稿来源链接校验：仅允许 http/https 协议（防 javascript: 等存储型 XSS）。空串放行。"""
    from urllib.parse import urlsplit

    url = (url or "").strip()
    if not url:
        return ""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("来源链接仅支持 http/https 协议")
    return url[:512]

router = APIRouter(prefix="/api/v1/candidate", tags=["candidate"])


def _jd_item(jd: JdLibrary, idx) -> dict:
    ind = idx.nodes.get(jd.industry_id) if jd.industry_id else None
    cat = idx.nodes.get(jd.category_id) if jd.category_id else None
    meta = (jd.jd_parsed or {}).get("meta") or {}
    return {
        "jd_id": str(jd.id),
        "title": jd.title,
        "company": jd.company,
        "city": jd.city,
        "education": jd.education,
        "salary_range": jd.salary_range,
        "industry": ind.name if ind else None,
        "category": cat.name if cat else None,
        "source": jd.source,
        "created_at": jd.created_at.isoformat() if jd.created_at else None,
        # 求稳赛道（M7.13）
        "stability": meta.get("stability"),
        "selection": meta.get("selection"),
        "exam_note": meta.get("exam_note"),
        "jd_tags": meta.get("tags") or [],
    }


@router.post("/recommend", response_model=RecommendOut)
async def recommend_route(
    file: UploadFile = File(...),
    top_n: int = Form(10),
    city: str = Form(""),
    session: AsyncSession = Depends(get_session),
) -> RecommendOut:
    """上传简历 → 岗位推荐（M7.10：city 为期望工作城市，同城优先）。"""
    filename = file.filename or "resume"
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if f".{suffix}" not in ALLOWED_SUFFIX:
        raise HTTPException(400, f"不支持的简历格式：.{suffix}（支持 pdf/doc/docx/txt）")
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "简历文件超过 20MB 限制")
    top_n = max(1, min(top_n, 20))

    tenant = await ensure_default_tenant(session)
    await ensure_seeded(session)

    # 简历文本提取（本地；放线程池避免阻塞事件循环）
    try:
        resume_text = await asyncio.to_thread(extract_text, filename, content)
    except DocExtractError as exc:
        raise HTTPException(400, f"简历解析失败：{exc}") from exc
    if not resume_text.strip():
        raise HTTPException(400, "未能从简历中提取到文本（文件可能为空/扫描件/仅图片内容，请检查后重试）")

    # 应届生结构化解析（DeepSeek；失败降级为空结构）
    warnings: list[str] = []
    parsed = {}
    settings = get_settings()
    llm = DeepSeekClient(settings) if settings.llm_configured else None
    if llm is not None:
        try:
            parsed = await parse_graduate(llm, resume_text)
        finally:
            await llm.aclose()
    else:
        warnings.append("未配置 DeepSeek API Key，采用本地关键词匹配（精度受限）")

    # 匹配（硬过滤 + TF-IDF 粗筛 + 结构化精排；向量精排可用时自动启用）
    from ...services.jobmatch.vector import get_reranker

    results = await recommend(
        session, parsed, resume_text, top_n=top_n, reranker=get_reranker(), prefer_city=city or None
    )
    auto_city = None
    pref = (parsed.get("basic_info") or {}).get("city_pref") or []
    if pref:
        auto_city = str(pref[0])

    # 简历落库 + 推荐记录
    stored_path = await save_resume_file(tenant.id, filename, content)
    basic = parsed.get("basic_info") or {}
    resume = Resume(
        tenant_id=tenant.id,
        candidate_name=basic.get("name"),
        file_name=filename,
        file_path=stored_path,
        file_type=suffix,
        source="candidate",
        parsed_text=resume_text,
        parsed_json=parsed,
        status="parsed",
    )
    session.add(resume)
    await session.flush()

    idx = await load_categories(session)
    items: list[RecommendationItem] = []
    for i, r in enumerate(results, start=1):
        jd: JdLibrary = r["jd"]
        reason = build_reason(r)
        rec = Recommendation(
            tenant_id=tenant.id,
            resume_id=resume.id,
            jd_id=jd.id,
            rank=i,
            match_score=r["match_score"],
            hit_skills=r["hit_skills"],
            missing_skills=r["missing_skills"],
            reason=reason,
        )
        session.add(rec)
        items.append(
            RecommendationItem(
                rank=i,
                match_score=r["match_score"],
                jd=JdLibraryItem(**_jd_item(jd, idx)),
                hit_skills=r["hit_skills"],
                missing_skills=r["missing_skills"],
                reason=reason,
                city_match=r.get("city_match", False),
                risk_flag=r.get("risk_flag", False),
            )
        )
    await session.commit()

    if not results:
        warnings.append("岗位库暂无匹配岗位，请稍后再试或扩充岗位库")

    return RecommendOut(
        resume_id=resume.id,
        resume_name=resume.candidate_name,
        total=len(items),
        items=items,
        warnings=warnings,
        prefer_city_auto=auto_city,
    )


@router.post("/direction-match", response_model=DirectionMatchOut)
async def direction_match_route(
    file: UploadFile = File(...),
    top_n: int = Form(6),
    session: AsyncSession = Depends(get_session),
) -> DirectionMatchOut:
    """校招方向匹配（M7.5）：无明确 JD 时，按岗位库聚合的方向画像推荐适合方向。

    零 LLM 成本：简历技能 × 方向核心技能覆盖率 + 赛道对位 + 工具链覆盖。
    """
    filename = file.filename or "resume"
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if f".{suffix}" not in ALLOWED_SUFFIX:
        raise HTTPException(400, f"不支持的简历格式：.{suffix}（支持 pdf/doc/docx/txt）")
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "简历文件超过 20MB 限制")
    top_n = max(1, min(top_n, 20))

    tenant = await ensure_default_tenant(session)
    await ensure_seeded(session)

    try:
        resume_text = await asyncio.to_thread(extract_text, filename, content)
    except DocExtractError as exc:
        raise HTTPException(400, f"简历解析失败：{exc}") from exc
    if not resume_text.strip():
        raise HTTPException(400, "未能从简历中提取到文本（文件可能为空/扫描件/仅图片内容，请检查后重试）")

    warnings: list[str] = []
    parsed = {}
    settings = get_settings()
    llm = DeepSeekClient(settings) if settings.llm_configured else None
    if llm is not None:
        try:
            parsed = await parse_graduate(llm, resume_text)
        finally:
            await llm.aclose()
    else:
        warnings.append("未配置 DeepSeek API Key，采用本地关键词匹配（精度受限）")

    # 简历画像（技能 + 赛道 + 专业→方向映射，M7.12）
    from ...services.jobmatch.direction import map_major_to_directions

    ontology = await load_ontology(session)
    resume_skills = set(str(s) for s in (parsed.get("skills") or [])) | scan_skills(resume_text, ontology)
    tracks = resume_tracks(parsed)
    idx = await load_categories(session)
    basic_info = parsed.get("basic_info") or {}
    major = str(basic_info.get("major") or "")
    major_dirs = map_major_to_directions(major)

    profiles = await build_direction_profiles(session)
    scored = [
        direction_match_score(resume_skills, tracks, p, idx, major_dirs=major_dirs, major=major)
        for p in profiles
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)

    stored_path = await save_resume_file(tenant.id, filename, content)
    basic = parsed.get("basic_info") or {}
    resume = Resume(
        tenant_id=tenant.id,
        candidate_name=basic.get("name"),
        file_name=filename,
        file_path=stored_path,
        file_type=suffix,
        source="candidate",
        parsed_text=resume_text,
        parsed_json=parsed,
        status="parsed",
    )
    session.add(resume)
    await session.commit()

    items = [
        DirectionItem(
            rank=i,
            score=s["score"],
            category_id=s["category_id"],
            name=s["name"],
            jd_count=s["jd_count"],
            hit_skills=s["hit_skills"],
            missing_skills=s["missing_skills"],
            core_skills=s["core_skills"],
            toolchain=s["toolchain"],
            reason=s["reason"],
            skill_scope=s["skill_scope"],
            low_barrier=s["low_barrier"],
        )
        for i, s in enumerate(scored[:top_n], start=1)
    ]
    return DirectionMatchOut(
        resume_id=resume.id,
        resume_name=resume.candidate_name,
        total=len(items),
        items=items,
        warnings=warnings,
    )


@router.post("/direction-score", response_model=ScoreOut)
async def direction_score_route(
    resume_id: uuid.UUID = Form(...),
    category_id: uuid.UUID = Form(...),
    weight_tier: str = Form("auto"),
    session: AsyncSession = Depends(get_session),
) -> ScoreOut:
    """方向级五维报告（M7.5）：以方向画像为伪 JD，复用证据抽取与确定性评分。"""
    tenant = await ensure_default_tenant(session)
    await ensure_seeded(session)

    resume = await session.get(Resume, resume_id)
    if resume is None or resume.tenant_id != tenant.id:
        raise HTTPException(404, "简历不存在")

    profiles = await build_direction_profiles(session)
    profile = next((p for p in profiles if p.category_id == category_id), None)
    if profile is None:
        raise HTTPException(404, "方向不存在或岗位库暂无该方向样本")

    parsed = resume.parsed_json or {}
    parsed_text = resume.parsed_text or ""
    tier = (
        suggest_tier(f"{profile.name}方向", None)
        if weight_tier in ("auto", "")
        else weight_tier
    )

    warnings: list[str] = []
    llm = DeepSeekClient(get_settings()) if get_settings().llm_configured else None
    evidence = {}
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
            warnings.append("未配置 DeepSeek API Key，采用本地证据与模板报告（精度受限）")
        if not evidence:
            evidence = fallback_evidence(parsed, parsed_text)

        from ...services.jobmatch.calibration import get_config

        cfg = await get_config(session)
        pseudo_jd = profile_to_pseudo_jd(profile)
        score = await compute_five_dim_scores(session, parsed, parsed_text, evidence, pseudo_jd, tier, cfg=cfg)

        if llm is not None:
            report_md = await generate_five_dim_report(
                llm, parsed, evidence, score, pseudo_jd.title, pseudo_jd.jd_text
            )
        else:
            from ...services.jobmatch.report import template_report

            report_md = template_report(parsed, evidence, score, pseudo_jd.title)
    finally:
        if llm is not None:
            await llm.aclose()

    detail = JdLibraryDetail(
        jd_id=pseudo_jd.id,
        title=pseudo_jd.title,
        company=pseudo_jd.company,
        city=None,
        education=None,
        salary_range=None,
        industry=None,
        category=profile.name,
        source="direction",
        jd_text=profile.text,
        skills=profile.all_skills,
        certs=[],
    )
    return ScoreOut(
        resume_id=resume.id,
        jd=detail,
        score=FiveDimScore(
            dimensions={k: DimensionDetail(**v) for k, v in score["dimensions"].items()},
            total_score=score["total_score"],
            max_score=score["max_score"],
            level=score["level"],
            tier=score["tier"],
            tier_label=score["tier_label"],
            doubts=score["doubts"],
            hit_skills=score["hit_skills"],
            missing_skills=score["missing_skills"],
        ),
        report_md=report_md,
        warnings=warnings,
        mode="direction",
        category_id=profile.category_id,
    )


@router.post("/resume-analysis", response_model=ResumeAnalysisOut)
async def resume_analysis_route(
    file: UploadFile = File(...),
    category_id: uuid.UUID | None = Form(None),
    jd_id: uuid.UUID | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> ResumeAnalysisOut:
    """校招简历优化分析（M7.6+）：纯简历侧诊断 + 五维优化建议。

    可选目标（针对性建议）：category_id=方向画像 或 jd_id=具体岗位；都不传则通用诊断。
    """
    filename = file.filename or "resume"
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if f".{suffix}" not in ALLOWED_SUFFIX:
        raise HTTPException(400, f"不支持的简历格式：.{suffix}（支持 pdf/doc/docx/txt）")
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "简历文件超过 20MB 限制")

    tenant = await ensure_default_tenant(session)
    try:
        resume_text = await asyncio.to_thread(extract_text, filename, content)
    except DocExtractError as exc:
        raise HTTPException(400, f"简历解析失败：{exc}") from exc
    if not resume_text.strip():
        raise HTTPException(400, "未能从简历中提取到文本（文件可能为空/扫描件/仅图片内容，请检查后重试）")

    # 构建目标信息（方向画像 / 岗位 JD）
    target = ""
    if category_id is not None:
        from ...services.jobmatch.direction import build_direction_profiles

        profiles = await build_direction_profiles(session)
        profile = next((p for p in profiles if p.category_id == category_id), None)
        if profile is not None:
            target = (
                f"目标方向：{profile.name}（岗位库 {profile.jd_count} 条样本）\n"
                f"方向核心技能：{'、'.join(profile.core_skills) or '（样本不足）'}\n"
                f"典型工具链：{'、'.join(profile.toolchain) or '—'}"
            )
    elif jd_id is not None:
        jd = await session.get(JdLibrary, jd_id)
        if jd is not None:
            target = f"目标岗位：{jd.title} @ {jd.company}\nJD 摘要：{jd.jd_text[:1500]}"

    warnings: list[str] = []
    parsed = {}
    settings = get_settings()
    llm = DeepSeekClient(settings) if settings.llm_configured else None
    analysis = {}
    try:
        if llm is not None:
            parsed = await parse_graduate(llm, resume_text)
        else:
            warnings.append("未配置 DeepSeek API Key，采用规则兜底分析（精度受限）")
        if llm is not None:
            from ...services.jobmatch.resume_analyze import analyze_resume

            analysis = await analyze_resume(llm, parsed, resume_text, target=target)
        else:
            from ...services.jobmatch.resume_analyze import fallback_analysis

            analysis = fallback_analysis(parsed)
    finally:
        if llm is not None:
            await llm.aclose()

    stored_path = await save_resume_file(tenant.id, filename, content)
    basic = parsed.get("basic_info") or {}
    resume = Resume(
        tenant_id=tenant.id,
        candidate_name=basic.get("name"),
        file_name=filename,
        file_path=stored_path,
        file_type=suffix,
        source="candidate",
        parsed_text=resume_text,
        parsed_json=parsed,
        status="parsed",
    )
    session.add(resume)
    await session.commit()

    return ResumeAnalysisOut(
        resume_id=resume.id,
        resume_name=resume.candidate_name,
        analysis=analysis,
        warnings=warnings,
    )


@router.post("/resume-rewrite", response_model=ResumeRewriteOut)
async def resume_rewrite_route(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> ResumeRewriteOut:
    """优化版简历生成（M7.7）：解析 + 优化建议 + LLM 改写为结构化内容（前端套多模板）。"""
    filename = file.filename or "resume"
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if f".{suffix}" not in ALLOWED_SUFFIX:
        raise HTTPException(400, f"不支持的简历格式：.{suffix}（支持 pdf/doc/docx/txt）")
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "简历文件超过 20MB 限制")

    tenant = await ensure_default_tenant(session)
    try:
        resume_text = await asyncio.to_thread(extract_text, filename, content)
    except DocExtractError as exc:
        raise HTTPException(400, f"简历解析失败：{exc}") from exc
    if not resume_text.strip():
        raise HTTPException(400, "未能从简历中提取到文本（文件可能为空/扫描件/仅图片内容，请检查后重试）")

    warnings: list[str] = []
    settings = get_settings()
    llm = DeepSeekClient(settings) if settings.llm_configured else None
    parsed, analysis, rewritten = {}, {}, {}
    try:
        if llm is None:
            warnings.append("未配置 DeepSeek API Key，无法生成优化版简历（需 LLM 改写）")
            raise HTTPException(503, "生成优化版简历需要配置 DeepSeek API Key")
        from ...services.jobmatch.parse import parse_graduate
        from ...services.jobmatch.resume_analyze import analyze_resume
        from ...services.jobmatch.resume_rewrite import rewrite_resume

        parsed = await parse_graduate(llm, resume_text)
        analysis = await analyze_resume(llm, parsed, resume_text)
        rewritten = await rewrite_resume(llm, parsed, analysis)
    finally:
        if llm is not None:
            await llm.aclose()

    stored_path = await save_resume_file(tenant.id, filename, content)
    basic = parsed.get("basic_info") or {}
    resume = Resume(
        tenant_id=tenant.id,
        candidate_name=basic.get("name"),
        file_name=filename,
        file_path=stored_path,
        file_type=suffix,
        source="candidate",
        parsed_text=resume_text,
        parsed_json=parsed,
        status="parsed",
    )
    session.add(resume)
    await session.commit()

    # 生成失败兜底：LLM 失败时 rewrite_resume 返回空结构，明确报错避免前端渲染空白简历
    if not any(
        rewritten.get(k) for k in ("personal", "summary", "education", "internships", "projects")
    ):
        raise HTTPException(502, "优化版简历生成失败，请稍后重试")

    return ResumeRewriteOut(
        resume_id=resume.id,
        resume_name=resume.candidate_name,
        content=rewritten,
        analysis=analysis,
        warnings=warnings,
    )


@router.post("/jd/crawl", response_model=CrawlOut)
async def crawl_jd(payload: CrawlIn, session: AsyncSession = Depends(get_session)) -> CrawlOut:
    """岗位库抓取（M7.8）：crawl4ai 抓取公开招聘页 → 入库 → 求职助手自动参与推荐/方向匹配。

    沙箱/受限环境（playwright 无法启动浏览器）时返回明确降级提示；生产环境无此限制。
    """
    await ensure_default_tenant(session)
    await ensure_seeded(session)
    from ...services.jobmatch.crawler import _check_safe_url, crawl_and_save

    # SSRF 防护：先逐条校验（协议 + 内网/环回/链路本地），任一不合法直接 400，
    # 避免"全部 URL 被跳过"时静默返回成功
    for u in payload.urls:
        try:
            await asyncio.to_thread(_check_safe_url, u)
        except ValueError as exc:
            raise HTTPException(400, f"抓取地址不合法：{exc}") from exc

    try:
        stats = await crawl_and_save(
            payload.urls,
            mode=payload.mode,
            limit=payload.limit,
            category=payload.category or "",
            industry=payload.industry or "",
            delay=payload.delay,
        )
    except PermissionError as exc:
        raise HTTPException(
            502,
            "当前环境无法启动浏览器内核（沙箱限制），请使用命令行脚本：python scripts/crawl_jobs.py "
            f"--mode {payload.mode} --url {payload.urls[0]} --limit {payload.limit}",
        ) from exc
    except ValueError as exc:
        # SSRF 防护：URL 协议/内网地址校验失败
        raise HTTPException(400, f"抓取地址不合法：{exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("jd crawl failed: %s", exc)
        raise HTTPException(502, "抓取失败，请检查网络或站点限制后重试") from exc
    total = await session.scalar(select(func.count()).select_from(JdLibrary)) or 0
    return CrawlOut(**stats, total_jd=total)


@router.post("/jd/submit", status_code=201)
async def submit_jd(
    company: str = Form(..., min_length=1, max_length=128),
    title: str = Form(..., min_length=1, max_length=128),
    jd_text: str = Form(..., min_length=30, max_length=20000),
    city: str = Form("", max_length=64),
    education: str = Form("", max_length=32),
    industry: str = Form("", max_length=64),
    category: str = Form("", max_length=64),
    source_url: str = Form("", max_length=512),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """岗位库投稿入口（docs/07-§4.3 P1，M7.4）：收录公开岗位 JD。"""
    tenant = await ensure_default_tenant(session)
    await ensure_seeded(session)

    # 来源链接协议校验（防存储型 XSS）
    try:
        source_url = _safe_http_url(source_url)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    # 去重：同 title + company + city 已存在则拒绝，防重复投稿灌库
    dup = await session.scalar(
        select(JdLibrary.id)
        .where(
            JdLibrary.title == title.strip(),
            JdLibrary.company == company.strip(),
            JdLibrary.city == (city.strip() or None),
        )
        .limit(1)
    )
    if dup:
        raise HTTPException(409, "该岗位已收录（相同标题/公司/城市），请勿重复投稿")

    idx = await load_categories(session)
    ind = next((c for c in idx.nodes.values() if c.dim == "industry" and c.name == industry), None)
    cat = next((c for c in idx.nodes.values() if c.dim == "function" and c.name == category), None)

    from ...services.jobmatch.matching import load_ontology, scan_certs, scan_skills

    ontology = await load_ontology(session)
    skills = sorted(scan_skills(jd_text, ontology))
    certs = sorted(scan_certs(jd_text, ontology))

    from datetime import datetime, timezone

    jd = JdLibrary(
        source="user_submit",
        source_url=source_url or None,
        company=company.strip(),
        industry_id=ind.id if ind else None,
        category_id=cat.id if cat else None,
        title=title.strip(),
        city=city.strip() or None,
        education=education.strip() or None,
        jd_text=jd_text.strip(),
        jd_parsed={
            "skills": skills,
            "certs": certs,
            "hard": {"education": education.strip() or None},
        },
        quality_score=0.5,  # 人工投稿，质量分低于精选种子
        is_active=True,
        crawl_at=datetime.now(timezone.utc),
    )
    session.add(jd)
    await session.commit()
    await session.refresh(jd)
    item = _jd_item(jd, idx)
    item["skills"] = skills
    item["certs"] = certs
    return item


@router.post("/score", response_model=ScoreOut)
async def score_route(
    resume_id: uuid.UUID = Form(...),
    jd_id: uuid.UUID = Form(...),
    weight_tier: str = Form("auto"),
    session: AsyncSession = Depends(get_session),
) -> ScoreOut:
    """对已解析简历 × 岗位库岗位做五维评分 + 生成报告（docs/07-§6/§7，M7.2）。"""
    tenant = await ensure_default_tenant(session)
    await ensure_seeded(session)

    resume = await session.get(Resume, resume_id)
    if resume is None or resume.tenant_id != tenant.id:
        raise HTTPException(404, "简历不存在")
    jd = await session.get(JdLibrary, jd_id)
    if jd is None or not jd.is_active:
        raise HTTPException(404, "岗位不存在")

    parsed = resume.parsed_json or {}
    parsed_text = resume.parsed_text or ""

    # 档位：auto → 按岗位自动建议
    idx = await load_categories(session)
    ind = idx.nodes.get(jd.industry_id) if jd.industry_id else None
    tier = suggest_tier(jd.title, ind.name if ind else None) if weight_tier in ("auto", "") else weight_tier

    # 证据抽取（LLM 优先，本地兜底）
    warnings: list[str] = []
    settings = get_settings()
    llm = DeepSeekClient(settings) if settings.llm_configured else None
    evidence = {}
    try:
        if llm is not None:
            jd_info = {
                "title": jd.title,
                "company": jd.company,
                "category": idx.nodes.get(jd.category_id).name if jd.category_id and idx.nodes.get(jd.category_id) else None,
                "industry": ind.name if ind else None,
                "jd_text": jd.jd_text,
                "jd_skills": (jd.jd_parsed or {}).get("skills") or [],
            }
            evidence = await extract_evidence(llm, parsed, jd_info)
        else:
            warnings.append("未配置 DeepSeek API Key，采用本地证据与模板报告（精度受限）")
        if not evidence:
            evidence = fallback_evidence(parsed, parsed_text)

        from ...services.jobmatch.calibration import get_config

        cfg = await get_config(session)
        score = await compute_five_dim_scores(session, parsed, parsed_text, evidence, jd, tier, cfg=cfg)

        # 报告（LLM 优先，模板兜底）
        if llm is not None:
            report_md = await generate_five_dim_report(
                llm, parsed, evidence, score, jd.title, jd.jd_text
            )
        else:
            from ...services.jobmatch.report import template_report

            report_md = template_report(parsed, evidence, score, jd.title)
    finally:
        if llm is not None:
            await llm.aclose()

    # 回写推荐记录（供 M7.3 校准闭环）
    reco = await session.scalar(
        select(Recommendation).where(
            Recommendation.tenant_id == tenant.id,
            Recommendation.resume_id == resume.id,
            Recommendation.jd_id == jd.id,
        )
    )
    if reco is not None:
        reco.score_result = score
        reco.status = "viewed"
    await session.commit()

    detail = JdLibraryDetail(**_jd_item(jd, idx))
    detail.jd_text = jd.jd_text
    detail.experience_required = jd.experience_required
    detail.skills = [str(s) for s in ((jd.jd_parsed or {}).get("skills") or [])]
    detail.certs = [str(c) for c in ((jd.jd_parsed or {}).get("certs") or [])]

    return ScoreOut(
        resume_id=resume.id,
        jd=detail,
        score=FiveDimScore(
            dimensions={
                k: DimensionDetail(**v)
                for k, v in score["dimensions"].items()
            },
            total_score=score["total_score"],
            max_score=score["max_score"],
            level=score["level"],
            tier=score["tier"],
            tier_label=score["tier_label"],
            doubts=score["doubts"],
            hit_skills=score["hit_skills"],
            missing_skills=score["missing_skills"],
        ),
        report_md=report_md,
        warnings=warnings,
    )


@router.get("/direction-profile")
async def direction_profile_meta(name: str, session: AsyncSession = Depends(get_session)) -> dict:
    """目标方向画像元数据（M7.15）：方向核心技能/工具链/样本数，供职业规划问卷勾选已会技能。"""
    await ensure_seeded(session)
    from ...services.jobmatch.career_plan import find_direction_profile

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
async def career_plan_route(payload: dict, session: AsyncSession = Depends(get_session)) -> dict:
    """职业规划（M7.15）：问卷 → 画像 + 差距 + 路线图 + 比赛/证书建议（目标限岗位库方向）。"""
    from ...services.engine.llm import DeepSeekClient
    from ...services.jobmatch.career_plan import compute_career_plan

    settings = get_settings()
    llm = DeepSeekClient(settings) if settings.llm_configured else None
    try:
        return await compute_career_plan(session, payload, llm=llm)
    finally:
        if llm is not None:
            await llm.aclose()


@router.get("/new-careers")
async def list_new_careers(
    q: str = "",
    group: str = "",
    major: str = "",
) -> dict:
    """国家新职业方向速览（M7.14）：信息参考层，不参与方向匹配打分。
    传 major 时按专业适配关键词相关性排序（fit_majors 命中越多越靠前）。"""
    from ...services.jobmatch.new_careers import GROUPS, DISCLAIMER, search_careers

    items = search_careers(q=q.strip(), group=group.strip(), major=major.strip())
    return {
        "groups": GROUPS,
        "disclaimer": DISCLAIMER,
        "total": len(items),
        "items": items,
    }


@router.get("/jd-library")
async def list_jd_library(
    category: str | None = None,
    industry: str | None = None,
    keyword: str | None = None,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """岗位库浏览/搜索（category/industry 传分类名，keyword 全文子串）。"""
    await ensure_seeded(session)
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    idx = await load_categories(session)
    cat_ids = [c.id for c in idx.nodes.values() if c.name == category] if category else None
    ind_ids = [c.id for c in idx.nodes.values() if c.name == industry] if industry else None

    conds = [JdLibrary.is_active == True]  # noqa: E712
    if cat_ids:
        conds.append(JdLibrary.category_id.in_(cat_ids))
    if ind_ids:
        conds.append(JdLibrary.industry_id.in_(ind_ids))
    if keyword:
        like = f"%{keyword}%"
        conds.append(or_(JdLibrary.title.like(like), JdLibrary.company.like(like), JdLibrary.jd_text.like(like)))

    total = (
        await session.scalar(select(func.count()).select_from(JdLibrary).where(*conds)) or 0
    )
    rows = (
        (
            await session.execute(
                select(JdLibrary)
                .where(*conds)
                .order_by(JdLibrary.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_jd_item(j, idx) for j in rows],
    }


@router.get("/categories")
async def list_categories(session: AsyncSession = Depends(get_session)) -> dict:
    """分类树：行业列表 + 职能树（一级职能 → 细分叶子）。"""
    await ensure_seeded(session)
    rows = (await session.execute(select(JdCategory).order_by(JdCategory.dim, JdCategory.level, JdCategory.sort_order))).scalars().all()
    industries = [{"id": str(r.id), "name": r.name} for r in rows if r.dim == "industry"]

    functions: dict[uuid.UUID, CategoryNode] = {}
    roots: list[CategoryNode] = []
    for r in rows:
        if r.dim != "function":
            continue
        node = CategoryNode(id=r.id, parent_id=r.parent_id, dim=r.dim, name=r.name, level=r.level)
        functions[r.id] = node
    for node in functions.values():
        if node.parent_id and node.parent_id in functions:
            functions[node.parent_id].children.append(node)
        else:
            roots.append(node)
    return {"industries": industries, "functions": [r.model_dump() for r in roots]}


@router.get("/jd/{jd_id}", response_model=JdLibraryDetail)
async def get_jd(jd_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> JdLibraryDetail:
    await ensure_seeded(session)
    jd = await session.get(JdLibrary, jd_id)
    if jd is None:
        raise HTTPException(404, "岗位不存在")
    idx = await load_categories(session)
    parsed = jd.jd_parsed or {}
    detail = JdLibraryDetail(**_jd_item(jd, idx))
    detail.jd_text = jd.jd_text
    detail.experience_required = jd.experience_required
    detail.skills = [str(s) for s in (parsed.get("skills") or [])]
    detail.certs = [str(c) for c in (parsed.get("certs") or [])]
    return detail


@router.get("/companies")
async def list_companies(
    kind: str | None = None,
    keyword: str | None = None,
    industry: str | None = None,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """公司避雷与推荐清单（M7.11）：kind=blacklist/recommended/warning。"""
    await ensure_default_tenant(session)
    from ...services.jobmatch.company_watch import DISCLAIMER, ensure_company_seed

    await ensure_company_seed(session)
    limit = max(1, min(limit, 200))
    conds = [CompanyWatchlist.status == "active"]  # noqa: E712
    if kind in ("blacklist", "recommended", "warning"):
        conds.append(CompanyWatchlist.kind == kind)
    if keyword:
        conds.append(CompanyWatchlist.company.like(f"%{keyword}%"))
    if industry:
        conds.append(CompanyWatchlist.industry == industry)
    total = await session.scalar(select(func.count()).select_from(CompanyWatchlist).where(*conds)) or 0
    rows = (
        (
            await session.execute(
                select(CompanyWatchlist)
                .where(*conds)
                .order_by(CompanyWatchlist.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    items = [
        CompanyItem(
            company_id=r.id,
            company=r.company,
            kind=r.kind,
            industry=r.industry,
            risk_level=r.risk_level,
            reason=r.reason,
            source_url=r.source_url,
            source=r.source,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]
    return {"total": total, "items": items, "disclaimer": DISCLAIMER}


@router.post("/companies", status_code=201)
async def submit_company(
    payload: CompanyIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """用户投稿公司避雷/推荐信息（M7.11：应届生互助共建）。"""
    await ensure_default_tenant(session)

    company = payload.company.strip()
    kind = payload.kind
    reason = (payload.reason or "").strip()
    industry = (payload.industry or "").strip()
    # 来源链接协议校验（防存储型 XSS：javascript: 等协议直接拒绝）
    try:
        source_url = _safe_http_url(payload.source_url or "")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    # 枚举与长度校验
    if kind not in ("blacklist", "recommended", "warning"):
        raise HTTPException(400, "kind 仅支持 blacklist / recommended / warning")
    if kind == "blacklist" and payload.risk_level not in ("高", "中", "低"):
        raise HTTPException(400, "risk_level 仅支持 高/中/低")
    if len(reason) > 500:
        raise HTTPException(400, "原因描述过长（≤500 字）")
    if len(industry) > 64:
        raise HTTPException(400, "领域名称过长（≤64 字）")

    # 去重：同公司同类型仅保留一条，防重复投稿污染公开清单
    dup = await session.scalar(
        select(CompanyWatchlist.id)
        .where(CompanyWatchlist.company == company, CompanyWatchlist.kind == kind)
        .limit(1)
    )
    if dup:
        raise HTTPException(409, f"「{company}」已存在同类条目，请勿重复提交")

    row = CompanyWatchlist(
        company=company,
        kind=kind,
        industry=industry or None,
        risk_level=payload.risk_level,
        reason=reason or None,
        source_url=source_url or None,
        source="user",
        status="active",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {
        "company_id": str(row.id),
        "company": row.company,
        "kind": row.kind,
        "note": "已收录，感谢共建；信息仅供参考，请自行核实",
    }
