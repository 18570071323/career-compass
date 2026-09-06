"""Pydantic 模型：工作流输出归一化为 MatchReport（docs/02-§3）。"""
from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field
Level = Literal["强烈推荐", "推荐", "待定", "不推荐", "无法评估"]

DEFAULT_DIMENSIONS = {
    "experience_match": ("经验匹配度", 40),
    "skill_match": ("技能匹配度", 25),
    "project_quality": ("项目质量", 20),
    "highlights": ("综合亮点", 15),
}


class DimensionScore(BaseModel):
    label: str
    score: float = Field(ge=0)
    max: float = Field(gt=0)


class ScoreResult(BaseModel):
    """工作流 score_result 的归一化结构。"""

    dimensions: dict[str, DimensionScore]
    total_score: float = Field(ge=0, le=100)
    max_score: float = Field(default=100, ge=1)
    level: Level


class MatchReport(BaseModel):
    """业务层统一输出。"""

    total_score: float | None = None
    max_score: float = 100
    level: Level | None = None
    dimensions: dict[str, DimensionScore] = {}
    parsed: dict[str, Any] | None = None  # 简历解析 JSON（v2 可选输出）
    deep_analysis: dict[str, Any] | None = None  # 深度人岗分析（含金量/风险/面试问题）
    report_md: str = ""
    source: Literal["workflow", "markdown_fallback", "llm", "mock", "failed"] = "workflow"
    warnings: list[str] = []


class AnalysisOut(BaseModel):
    """单份分析 API 响应。"""

    analysis_id: uuid.UUID
    status: str
    trigger: str
    job_id: uuid.UUID
    resume_id: uuid.UUID
    report: MatchReport
    error_msg: str | None = None


class JobCreate(BaseModel):
    """创建岗位请求。"""

    title: str | None = None
    department: str | None = None
    jd_text: str


class CompareSetCreate(BaseModel):
    """创建多候选人对比集请求。"""

    name: str | None = None
    job_id: uuid.UUID
    resume_ids: list[uuid.UUID]


class RefreshRuleUpdate(BaseModel):
    """刷新/激活规则更新请求（字段均可选）。"""

    refresh_interval_days: int | None = Field(default=None, ge=1, le=365)
    expire_days: int | None = Field(default=None, ge=1, le=3650)
    activation_threshold: int | None = Field(default=None, ge=0, le=100)
    max_analysis_per_job: int | None = Field(default=None, ge=1, le=500)
    enabled: bool | None = None
    notify_email: bool | None = None


class JobUpdate(BaseModel):
    """岗位更新请求（M4：开/关状态）。"""

    status: Literal["open", "closed"] | None = None
    title: str | None = None


class HitUpdate(BaseModel):
    """潜在人选状态更新请求。"""

    status: Literal["new", "viewed", "contacted", "archived"]


class CozeConnect(BaseModel):
    """保存 Coze OAuth 应用配置。"""

    client_id: str
    client_secret: str | None = None
    workspace_id: str | None = None


class CozeBind(BaseModel):
    """绑定 Coze 工作流。"""

    workflow_id: str


class RegisterRequest(BaseModel):
    """注册请求。"""

    company_name: str
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    """登录请求。"""

    email: str
    password: str


class OrderCreate(BaseModel):
    """创建套餐订单请求。"""

    plan: str  # pro / enterprise
    months: int = Field(default=1, ge=1)


class MpLoginRequest(BaseModel):
    """小程序 wx.login 请求。"""

    code: str
    nickname: str | None = None


class MpGuideRequest(BaseModel):
    """求职导航请求（个性化信息，均可选，字段缺省时 AI 标注信息不足）。"""

    target_job: str | None = None
    years: str | None = None
    city: str | None = None
    industry: str | None = None
    goal: str | None = None
    self_intro: str | None = None


# ---------- C 端应届生求职（docs/07） ----------


class JdLibraryItem(BaseModel):
    """岗位库列表项。"""

    jd_id: uuid.UUID
    title: str
    company: str
    city: str | None = None
    education: str | None = None
    salary_range: str | None = None
    industry: str | None = None
    category: str | None = None
    source: str = "manual"
    created_at: str | None = None
    # 求稳赛道（M7.13）
    stability: str | None = None  # bank（银行）/ soe（央国企）/ None
    selection: str | None = None  # exam（考试制）/ direct（投递制）/ mixed
    exam_note: str | None = None  # 选拔流程提示（如"网申→笔试→面试"）
    jd_tags: list[str] = []  # 展示标签，如 ["银行", "柜员", "求稳"]


class JdLibraryDetail(JdLibraryItem):
    jd_text: str = ""
    experience_required: str | None = None
    skills: list[str] = []
    certs: list[str] = []


class RecommendationItem(BaseModel):
    """单条岗位推荐。"""

    rank: int
    match_score: float
    jd: JdLibraryItem
    hit_skills: list[str] = []
    missing_skills: list[str] = []
    reason: str = ""
    city_match: bool = False  # 是否匹配期望城市（M7.10）
    risk_flag: bool = False  # 该公司有避雷记录（M7.11）


class CompanyItem(BaseModel):
    """公司避雷/推荐清单项（M7.11）。"""

    company_id: uuid.UUID
    company: str
    kind: str  # blacklist/recommended/warning
    industry: str | None = None
    risk_level: str | None = None
    reason: str | None = None
    source_url: str | None = None
    source: str = "manual"
    created_at: str | None = None


class CompanyIn(BaseModel):
    """用户投稿公司信息。"""

    company: str = Field(min_length=1, max_length=128)
    kind: str = Field(pattern="^(blacklist|recommended|warning)$")
    industry: str | None = None
    risk_level: str | None = None
    reason: str = Field(min_length=5)
    source_url: str | None = None


class RecommendOut(BaseModel):
    """简历 → 推荐岗位响应。"""

    resume_id: uuid.UUID
    resume_name: str | None = None
    total: int
    items: list[RecommendationItem]
    warnings: list[str] = []
    prefer_city_auto: str | None = None  # 简历解析出的期望城市（前端默认填充）


class CategoryNode(BaseModel):
    """分类树节点（含子节点）。"""

    id: uuid.UUID
    parent_id: uuid.UUID | None = None
    dim: str
    name: str
    level: int = 1
    children: list["CategoryNode"] = []


class DimensionDetail(BaseModel):
    """五维评分中的单个维度（含分项拆解）。"""

    label: str
    score: float = 0.0
    max: float = 0.0
    breakdown: dict[str, float] = {}


class FiveDimScore(BaseModel):
    """五维评分结果（M7.2）。"""

    dimensions: dict[str, DimensionDetail]
    total_score: float = 0.0
    max_score: float = 100.0
    level: str = ""
    tier: str = "default"
    tier_label: str = ""
    doubts: list[str] = []
    hit_skills: list[str] = []
    missing_skills: list[str] = []


class ScoreOut(BaseModel):
    """五维评分 + 报告响应。"""

    resume_id: uuid.UUID
    jd: JdLibraryDetail
    score: FiveDimScore
    report_md: str = ""
    warnings: list[str] = []
    mode: str = "jd"  # jd（社招/明确 JD）/ direction（校招方向模式）
    category_id: uuid.UUID | None = None  # direction 模式下的方向分类 id（重算用）


class DirectionItem(BaseModel):
    """校招方向匹配项（M7.5：无明确 JD 时按方向画像匹配）。"""

    rank: int
    score: float
    category_id: uuid.UUID
    name: str
    jd_count: int = 0
    hit_skills: list[str] = []
    missing_skills: list[str] = []
    core_skills: list[str] = []
    toolchain: list[str] = []
    reason: str = ""
    # 门槛提示（M7.13）：技能要求少的方向分易虚高
    skill_scope: int = 0  # 方向技能集大小
    low_barrier: bool = False  # 是否低门槛（技能集 <6）


class DirectionMatchOut(BaseModel):
    """方向匹配响应。"""

    resume_id: uuid.UUID
    resume_name: str | None = None
    total: int
    items: list[DirectionItem]
    warnings: list[str] = []


class ResumeAnalysisOut(BaseModel):
    """校招简历优化分析响应（M7.6：诊断 + 优化建议，不依赖 JD）。"""

    resume_id: uuid.UUID
    resume_name: str | None = None
    analysis: dict = {}
    warnings: list[str] = []


class ResumeRewriteOut(BaseModel):
    """优化版简历生成响应（M7.7：结构化内容，前端套多模板风格渲染）。"""

    resume_id: uuid.UUID
    resume_name: str | None = None
    content: dict = {}
    analysis: dict = {}
    warnings: list[str] = []


class CrawlIn(BaseModel):
    """岗位库抓取请求（M7.8：crawl4ai 接入求职助手）。"""

    urls: list[str] = Field(min_length=1, max_length=5)
    mode: str = Field(default="default", pattern="^(default|lever)$")
    category: str | None = None
    industry: str | None = None
    limit: int = Field(default=10, ge=1, le=20)
    delay: float = Field(default=1.5, ge=0, le=10)


class CrawlOut(BaseModel):
    """岗位库抓取响应。"""

    listed: int = 0
    fetched: int = 0
    saved: int = 0
    failed: int = 0
    total_jd: int = 0  # 抓取后岗位库总数
