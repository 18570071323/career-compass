"""岗位库 JD 抓取服务（crawl4ai skill，docs/07-§20）。

供两个入口共用：
- CLI：apps/api/scripts/crawl_jobs.py
- API：POST /api/v1/candidate/jd/crawl（求职助手「扩充岗位库」）

核心链路：列表页（schema / Markdown 正则）→ 详情页 JD 正文 → 入库 jd_library，
抓取岗位带「英文→中文职能叶子」映射，保证参与方向画像与简历推荐。
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import re
import socket
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _is_unsafe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """私网/环回/链路本地/保留/组播/未指定地址一律视为不安全（SSRF 防护）。"""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _check_safe_host(host: str, source: str) -> None:
    """拒绝解析目标为内网/环回/链路本地/保留地址的主机。域名会解析全部 A/AAAA 记录检查。"""
    try:
        ip = ipaddress.ip_address(host)  # 主机名本身是 IP
        if _is_unsafe_ip(ip):
            raise ValueError(f"{source} 命中内网/保留地址: {host}")
        return
    except ValueError as exc:
        if str(exc).startswith(source):
            raise
    # 域名 → 解析所有记录，任一命中内网即拒绝
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"{source} 域名无法解析: {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if _is_unsafe_ip(ip):
            raise ValueError(f"{source} 域名解析到内网地址: {host} -> {ip}")


def _check_safe_url(url: str) -> str:
    """校验抓取 URL：仅 http/https，且目标主机不在内网。返回 strip 后的 URL，不合法抛 ValueError。"""
    url = (url or "").strip()
    if not url:
        raise ValueError("URL 为空")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"仅允许 http/https 协议: {url[:80]}")
    if not parts.hostname:
        raise ValueError(f"URL 缺少主机名: {url[:80]}")
    _check_safe_host(parts.hostname, f"URL {url[:60]}")
    return url


async def _check_safe_url_async(url: str) -> str:
    """异步版 URL 校验（DNS 解析放线程池，避免阻塞事件循环）。"""
    return await asyncio.to_thread(_check_safe_url, url)

# 沙箱友好：crawl4ai 数据目录与 Playwright 内核指向仓库 .tools（必须在 import crawl4ai 前设置）
# 本文件位于 apps/api/app/services/jobmatch/ → parents[5] 为仓库根
_ROOT = Path(__file__).resolve().parents[5]
os.environ.setdefault("CRAWL4_AI_BASE_DIRECTORY", str(_ROOT / ".tools" / "crawl4ai"))
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_ROOT / ".tools" / "pw-browsers"))

# 列表页岗位卡片提取 schema（默认）
DEFAULT_LIST_SCHEMA: dict[str, Any] = {
    "name": "jobs",
    "baseSelector": "a[href*='job'], .job-card, .job-item, li[class*='job']",
    "fields": [
        {"name": "title", "selector": "h1, h2, h3, .title, [class*='title']", "type": "text"},
        {"name": "company", "selector": "[class*='company'], [class*='org']", "type": "text"},
        {"name": "city", "selector": "[class*='city'], [class*='location']", "type": "text"},
        {"name": "url", "selector": "a", "type": "attribute", "attribute": "href"},
    ],
}

# Lever ATS 列表 schema
LEVER_LIST_SCHEMA: dict[str, Any] = {
    "name": "jobs",
    "baseSelector": "a.posting-title",
    "fields": [
        {"name": "title", "selector": "a.posting-title", "type": "text"},
        {"name": "url", "selector": "a.posting-title", "type": "attribute", "attribute": "href"},
    ],
}

DEFAULT_CONTENT_SELECTOR = "main, article, .job-description, .jd, [class*='description'], [class*='content']"
LEVER_CONTENT_SELECTOR = ".posting-description, .posting-page"

# 英文岗位标题 → 中文职能叶子（使抓取岗位参与方向画像与赛道匹配）
# 顺序敏感：先命中优先；关键词收窄避免误匹配（如 account executive ≠ accountant）
EN_TITLE_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"data (scientist|analyst|engineer)|business analyst|bi analyst", re.I), "数据分析"),
    (re.compile(r"machine learning|nlp|algorithm|ai (engineer|scientist)|deep learning|computer vision", re.I), "算法工程师"),
    (re.compile(r"front[- ]?end|web (ui|front)|react|vue|ui developer|ux engineer", re.I), "前端开发"),
    (re.compile(r"back[- ]?end|full[- ]?stack|software engineer|java|golang|python engineer|backend|developer", re.I), "后端开发"),
    (re.compile(r"qa|quality|test (engineer|automation)", re.I), "测试"),
    (re.compile(r"site reliability|sre|infrastructure|system engineer|cloud engineer", re.I), "运维"),
    (re.compile(r"product manager|product designer|project manager", re.I), "产品经理"),
    (re.compile(r"account executive|business development|sales", re.I), "市场营销"),
    (re.compile(r"user operation|community|growth", re.I), "用户运营"),
    (re.compile(r"content strategist|copywriter|editor|writer", re.I), "内容运营"),
    (re.compile(r"marketing|brand|pr|public relation|media|seo", re.I), "市场营销"),
    (re.compile(r"hr|human resource|recruit|talent", re.I), "人力资源"),
    (re.compile(r"finance|financial|accountant|accounting|controller|tax|audit", re.I), "财务"),
    (re.compile(r"legal|counsel|compliance", re.I), "法务"),
    (re.compile(r"admin|office manager", re.I), "行政"),
]


def map_title_to_category(title: str) -> str | None:
    """英文/混合岗位标题 → 中文职能叶子名（顺序匹配，命中最先）。"""
    low = title.lower()
    for pattern, name in EN_TITLE_MAP:
        if pattern.search(low):
            return name
    return None


async def fetch_list_page(crawler, url: str, schema: dict, limit: int) -> list[dict]:
    """抓取岗位列表页：schema 提取优先，Markdown 正则回退。"""
    from crawl4ai import CacheMode, CrawlerRunConfig
    from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

    config = CrawlerRunConfig(
        extraction_strategy=JsonCssExtractionStrategy(schema=schema),
        page_timeout=30000,
        cache_mode=CacheMode.DISABLED,
        remove_overlay_elements=True,
    )
    result = await crawler.arun(url=url, config=config)
    if not result.success:
        logger.warning("列表页抓取失败 %s: %s", url, result.error_message)
        return []
    # 重定向防护：跟随跳转后的最终地址同样必须安全
    final_url = (result.url or url).strip()
    if final_url != url:
        try:
            await _check_safe_url_async(final_url)
        except ValueError as exc:
            logger.warning("列表页重定向目标不安全，丢弃 %s: %s", url, exc)
            return []

    cards: list[dict] = []
    extracted = result.extracted_content or "[]"
    try:
        items = json.loads(extracted)
    except json.JSONDecodeError:
        items = []
    for it in items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        cards.append(
            {
                "title": title,
                "company": (it.get("company") or "").strip(),
                "city": (it.get("city") or "").strip(),
                "url": (it.get("url") or "").strip(),
            }
        )

    # Markdown 正则回退（[岗位名](详情url) 形态，Lever/ATS 通用；仅保留 uuid 详情链接）
    if not cards:
        md = result.markdown or ""
        for m in re.finditer(r"\[([^\]]{3,90})\]\((https?://[^)\s]+)\)", md):
            title = m.group(1).strip()
            link = m.group(2).strip()
            if not title or "?" in link:
                continue
            if not re.search(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", link):
                continue
            cards.append({"title": title, "company": "", "city": "", "url": link})
    return cards[:limit]


async def fetch_jd_text(crawler, url: str, content_selector: str | None) -> str:
    """抓取岗位详情页 JD 正文（Markdown 过滤，≤6000 字）。"""
    from crawl4ai import CacheMode, CrawlerRunConfig

    kw: dict[str, Any] = {"page_timeout": 40000, "remove_overlay_elements": True, "cache_mode": CacheMode.DISABLED}
    if content_selector:
        kw["css_selector"] = content_selector
    config = CrawlerRunConfig(**kw)
    result = await crawler.arun(url=url, config=config)
    if not result.success:
        logger.warning("详情页抓取失败 %s: %s", url, result.error_message)
        return ""
    # 重定向防护：最终地址必须安全
    final_url = (result.url or url).strip()
    if final_url != url:
        try:
            await _check_safe_url_async(final_url)
        except ValueError as exc:
            logger.warning("详情页重定向目标不安全，丢弃 %s: %s", url, exc)
            return ""
    return (result.markdown or "").strip()[:6000]


async def save_to_library(
    session,
    jd_data: dict,
    *,
    map_category: bool = True,
    source: str = "crawler",
) -> uuid.UUID | None:
    """写入 jd_library（技能/证书扫描 + 分类映射）。"""
    from sqlalchemy import select

    from app.models import JdCategory, JdLibrary
    from app.services.jobmatch.matching import load_ontology, scan_certs, scan_skills

    text = jd_data.get("jd_text") or ""
    if len(text) < 30:
        logger.warning("JD 文本过短，跳过：%s", jd_data.get("title"))
        return None

    ontology = await load_ontology(session)
    skills = sorted(scan_skills(text, ontology))
    certs = sorted(scan_certs(text, ontology))

    category_id = None
    cat_name = jd_data.get("category") or ""
    if not cat_name and map_category:
        cat_name = map_title_to_category(jd_data.get("title") or "") or ""
    if cat_name:
        cat = await session.scalar(
            select(JdCategory).where(JdCategory.dim == "function", JdCategory.name == cat_name)
        )
        category_id = cat.id if cat else None

    industry_id = None
    if jd_data.get("industry"):
        ind = await session.scalar(
            select(JdCategory).where(JdCategory.dim == "industry", JdCategory.name == jd_data["industry"])
        )
        industry_id = ind.id if ind else None

    # 爬虫去重：同 source_url 已存在则更新内容而非新增（防重复抓取产生重复岗位/方向画像失真）
    url = jd_data.get("url") or None
    if source == "crawler" and url:
        existing = await session.scalar(
            select(JdLibrary.id).where(
                JdLibrary.source == "crawler", JdLibrary.source_url == url
            ).limit(1)
        )
        if existing is not None:
            jd = await session.get(JdLibrary, existing)
            jd.jd_text = text
            jd.jd_parsed = {"skills": skills, "certs": certs, "hard": {}}
            jd.crawl_at = datetime.now(timezone.utc)
            await session.flush()
            logger.info("更新已有岗位: %s @ %s", jd.title, jd.company)
            return jd.id

    jd = JdLibrary(
        source=source,
        source_url=url,
        company=jd_data.get("company") or "未知企业",
        industry_id=industry_id,
        category_id=category_id,
        title=jd_data["title"][:120],
        city=jd_data.get("city") or None,
        education=None,
        jd_text=text,
        jd_parsed={"skills": skills, "certs": certs, "hard": {}},
        quality_score=0.6,
        is_active=True,
        crawl_at=datetime.now(timezone.utc),
    )
    session.add(jd)
    await session.flush()
    logger.info(
        "入库: %s @ %s | category=%s | skills=%d",
        jd.title, jd.company, cat_name or category_id, len(skills),
    )
    return jd.id


async def crawl_and_save(
    urls: list[str],
    *,
    mode: str = "default",
    limit: int = 10,
    category: str = "",
    industry: str = "",
    delay: float = 1.5,
    content_selector: str | None = None,
) -> dict[str, int]:
    """抓取并入库。返回统计 {listed, fetched, saved, failed}。"""
    from crawl4ai import AsyncWebCrawler, BrowserConfig

    from app.db import SessionLocal

    if mode == "lever":
        list_schema, jd_selector = LEVER_LIST_SCHEMA, LEVER_CONTENT_SELECTOR
    else:
        list_schema, jd_selector = DEFAULT_LIST_SCHEMA, content_selector or DEFAULT_CONTENT_SELECTOR

    browser = BrowserConfig(headless=True, viewport_width=1440, viewport_height=900)
    stats = {"listed": 0, "fetched": 0, "saved": 0, "failed": 0}

    async with AsyncWebCrawler(config=browser) as crawler, SessionLocal() as session:
        for raw_url in urls:
            try:
                url = await _check_safe_url_async(raw_url)
            except ValueError as exc:
                logger.warning("跳过不安全的列表页 URL %r: %s", raw_url, exc)
                stats["failed"] += 1
                continue
            logger.info("抓取列表页: %s", url)
            cards = await fetch_list_page(crawler, url, list_schema, limit)
            stats["listed"] += len(cards)
            for card in cards:
                # 详情链接：相对路径先相对列表页归一化，再做安全校验
                raw_detail = card.get("url") or ""
                try:
                    detail_url = await _check_safe_url_async(
                        urllib.parse.urljoin(url, raw_detail) if raw_detail else url
                    )
                except ValueError as exc:
                    logger.warning("跳过不安全的详情 URL %r: %s", raw_detail[:80], exc)
                    stats["failed"] += 1
                    continue
                logger.info("抓取详情: %s (%s)", card["title"], detail_url[:80])
                text = await fetch_jd_text(crawler, detail_url, jd_selector)
                stats["fetched"] += 1
                if not text:
                    stats["failed"] += 1
                    continue
                jd_id = await save_to_library(
                    session,
                    {**card, "url": detail_url, "jd_text": text, "category": category, "industry": industry},
                )
                if jd_id:
                    stats["saved"] += 1
                else:
                    stats["failed"] += 1
                if delay > 0:
                    await __import__("asyncio").sleep(delay)  # 合规：请求间隔
        await session.commit()
    return stats
