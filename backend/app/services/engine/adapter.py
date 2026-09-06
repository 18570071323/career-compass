"""自研匹配引擎（路线 2）：本地解析 → LLM 抽取 → 确定性评分 → LLM 报告。

与 Coze 解耦：产品核心能力完全自持，Coze 工作流仅作为可选的备用引擎。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...schemas import MatchReport
from ..coze.adapter import CozeConnection, CozeResumeMatcherAdapter
from ..coze.connection import resolve_connection
from .doc_extract import DocExtractError, extract_text
from .llm import DeepSeekClient, LLMError
from .scoring import compute_scores

logger = logging.getLogger(__name__)

MOCK_REPORT_MD = """# 简历评估报告

## 候选人概况
（演示模式：未配置 DeepSeek API Key，以下为示例数据。）

## 评分总览
| 维度 | 得分 | 满分 |
|------|------|------|
| 经验匹配度 | 30 | 40 |
| 技能匹配度 | 21 | 25 |
| 项目质量 | 16 | 20 |
| 综合亮点 | 11 | 15 |

**总分：78/100**
**推荐等级：推荐**

## 详细分析
（演示报告正文）

## 优势
- 演示优势 1
- 演示优势 2

## 不足与风险
- 演示风险 1

## 录用建议
推荐（演示）
"""


class ResumeMatchAdapter(Protocol):
    """匹配引擎统一接口：简历文件 + JD → MatchReport。"""

    async def analyze(
        self,
        *,
        resume_bytes: bytes,
        filename: str,
        jd_text: str,
        report_lang: str = "auto",
    ) -> MatchReport:
        ...


def detect_lang(text: str) -> str:
    """简单语言检测：中文字符占比 > 10% 视为中文，否则英文。"""
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return "zh" if text and cjk / len(text) > 0.1 else "en"


class LLMEngineAdapter:
    """主引擎：文档提取 → DeepSeek 解析 → 评分 → 深度分析 → 报告。"""

    def __init__(self, llm: DeepSeekClient) -> None:
        self._llm = llm

    async def analyze(
        self,
        *,
        resume_bytes: bytes,
        filename: str,
        jd_text: str,
        report_lang: str = "auto",
    ) -> MatchReport:
        try:
            resume_text = await asyncio.to_thread(extract_text, filename, resume_bytes)
        except DocExtractError as exc:
            return MatchReport(report_md=f"（文档解析失败：{exc}）", source="failed", warnings=[str(exc)])
        if not resume_text.strip():
            return MatchReport(report_md="（未能从简历中提取到文本）", source="failed", warnings=["空文本"])

        lang = detect_lang(resume_text) if report_lang == "auto" else report_lang
        parsed = await self._llm.parse_resume(resume_text, jd_text)
        score = compute_scores(parsed)
        score_json = score.model_dump(mode="json")
        deep: dict[str, Any] | None = None
        try:
            deep = await self._llm.deep_analyze(parsed, score_json, jd_text)
        except LLMError:
            logger.warning("deep analysis failed, continue without it", exc_info=True)
        report_md = await self._llm.generate_report(parsed, score_json, jd_text, lang=lang)
        return MatchReport(
            total_score=score.total_score,
            max_score=score.max_score,
            level=score.level,
            dimensions=score.dimensions,
            parsed=parsed,
            report_md=report_md,
            deep_analysis=deep,
            source="llm",
            warnings=[],
        )


class MockAdapter:
    """演示模式：无任何引擎配置时返回模拟报告。"""

    async def analyze(
        self,
        *,
        resume_bytes: bytes,
        filename: str,
        jd_text: str,
        report_lang: str = "auto",
    ) -> MatchReport:
        return MatchReport(
            total_score=78.0,
            max_score=100,
            level="推荐",
            dimensions={
                "experience_match": {"label": "经验匹配度", "score": 30.0, "max": 40.0},
                "skill_match": {"label": "技能匹配度", "score": 21.0, "max": 25.0},
                "project_quality": {"label": "项目质量", "score": 16.0, "max": 20.0},
                "highlights": {"label": "综合亮点", "score": 11.0, "max": 15.0},
            },
            report_md=MOCK_REPORT_MD,
            source="mock",
            warnings=[],
        )


async def build_engine(session: AsyncSession, tenant_id: uuid.UUID) -> ResumeMatchAdapter:
    """按租户解析引擎：租户 OAuth Coze → 环境 DeepSeek → 环境 Coze → mock。"""
    settings = get_settings()

    # 1) 租户级 Coze OAuth（若客户自带工作流）
    connection = await resolve_connection(session, tenant_id)
    if connection is not None:
        return CozeResumeMatcherAdapter(connection)

    # 2) 环境 DeepSeek（主引擎）
    if settings.llm_configured:
        return LLMEngineAdapter(DeepSeekClient(settings))

    # 3) 环境 Coze（备用）
    if settings.coze_configured:
        return CozeResumeMatcherAdapter(
            CozeConnection(
                base_url=settings.coze_base_url,
                token=settings.coze_api_token,
                workflow_id=settings.coze_workflow_id,
            )
        )

    # 4) 演示模式
    return MockAdapter()
