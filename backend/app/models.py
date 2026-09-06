"""核心数据模型（对齐 docs/02-data-model.md）。

注意：当前为多租户 SaaS 的完整实体集合，M1 阶段先保证结构正确，
路由层暂以默认租户跑通链路，M5 再接入完整鉴权。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# PostgreSQL 用 JSONB；其他方言（如本地 SQLite 联调）自动退回 JSON
JSONType = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    """企业租户。"""

    __tablename__ = "tenant"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128))
    plan: Mapped[str] = mapped_column(String(32), default="free")  # free/pro/enterprise
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active/disabled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    """企业用户。"""

    __tablename__ = "user"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    email: Mapped[str] = mapped_column(String(128), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="recruiter")  # admin/recruiter/viewer
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Job(Base):
    """岗位（JD 文本即工作流 jd_text 入参来源）。"""

    __tablename__ = "job"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    title: Mapped[str] = mapped_column(String(128))
    department: Mapped[str | None] = mapped_column(String(64), nullable=True)
    jd_text: Mapped[str] = mapped_column(Text)
    jd_file_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    keywords: Mapped[dict | None] = mapped_column(JSONType, nullable=True)  # 预筛关键词（本地提取）
    status: Mapped[str] = mapped_column(String(16), default="open")  # open/closed/archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Resume(Base):
    """简历 / 候选人（简历库）。"""

    __tablename__ = "resume"
    __table_args__ = (Index("ix_resume_tenant_status", "tenant_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    candidate_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    file_type: Mapped[str] = mapped_column(String(16))  # pdf/docx
    source: Mapped[str] = mapped_column(String(16), default="upload")  # upload/manual/import/ats
    parsed_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # 本地提取文本（预筛用）
    parsed_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)  # 工作流 parsed_resume
    status: Mapped[str] = mapped_column(String(16), default="new")
    # new → parsed → analyzed → expired → activated（见 docs/02-§2.4）
    tags: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Analysis(Base):
    """匹配分析记录（核心表）：一份简历 × 一个岗位 = 一次分析。"""

    __tablename__ = "analysis"
    __table_args__ = (
        Index("ix_analysis_tenant_job", "tenant_id", "job_id"),
        Index("ix_analysis_tenant_resume", "tenant_id", "resume_id"),
        Index("ix_analysis_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job.id"))
    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resume.id"))
    batch_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("batch_job.id"), nullable=True
    )
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual/batch/auto_refresh/mining
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued/running/completed/failed/cancelled
    score_result: Mapped[dict | None] = mapped_column(JSONType, nullable=True)  # 归一化分数 MatchReport.score_result
    report_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    deep_analysis: Mapped[dict | None] = mapped_column(JSONType, nullable=True)  # 深度人岗分析（含金量/风险/面试问题）
    coze_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    coze_raw: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BatchJob(Base):
    """批量任务（批量分析 / 刷新 / 挖掘）。"""

    __tablename__ = "batch_job"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16), default="batch_analysis")  # batch_analysis/refresh/mining
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/running/completed/failed/partial
    total: Mapped[int] = mapped_column(Integer, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error_summary: Mapped[dict | None] = mapped_column(JSONType, nullable=True)  # 文件→失败原因
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompareSet(Base):
    """多候选人对比集。"""

    __tablename__ = "compare_set"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job.id"))
    settings: Mapped[dict | None] = mapped_column(JSONType, nullable=True)  # 维度权重/展示配置
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CompareSetItem(Base):
    __tablename__ = "compare_set_item"
    __table_args__ = (UniqueConstraint("compare_set_id", "resume_id", name="uq_compare_resume"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    compare_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("compare_set.id"))
    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resume.id"))
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis.id"), nullable=True)
    order_idx: Mapped[int] = mapped_column(Integer, default=0)


class CandidateHit(Base):
    """潜在人选命中（岗位找人 / 人找岗位）。"""

    __tablename__ = "candidate_hit"
    __table_args__ = (Index("ix_hit_job_score", "job_id", "total_score"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job.id"), nullable=True)  # 人找岗位时为空
    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resume.id"))
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis.id"), nullable=True)
    total_score: Mapped[int] = mapped_column(Integer, default=0)  # 冗余便于排序
    hit_type: Mapped[str] = mapped_column(String(16), default="job_to_candidate")  # job_to_candidate/candidate_to_job
    status: Mapped[str] = mapped_column(String(16), default="new")  # new/viewed/contacted/archived
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RefreshRule(Base):
    """简历库刷新/激活规则（租户级）。"""

    __tablename__ = "refresh_rule"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), unique=True)
    refresh_interval_days: Mapped[int] = mapped_column(Integer, default=7)
    expire_days: Mapped[int] = mapped_column(Integer, default=30)
    activation_threshold: Mapped[int] = mapped_column(Integer, default=60)
    max_analysis_per_job: Mapped[int] = mapped_column(Integer, default=20)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=False)


class CozeConfig(Base):
    """Coze 连接配置（system 级默认 / tenant 级覆盖）。"""

    __tablename__ = "coze_config"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    scope: Mapped[str] = mapped_column(String(16), default="system")  # system/tenant
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenant.id"), nullable=True)
    base_url: Mapped[str] = mapped_column(String(128), default="https://api.coze.cn")
    workflow_id: Mapped[str] = mapped_column(String(64))
    api_token_enc: Mapped[str] = mapped_column(String(512))  # AES-GCM 加密存储
    file_input_key: Mapped[str] = mapped_column(String(32), default="resume_file")
    jd_input_key: Mapped[str] = mapped_column(String(32), default="jd_text")
    report_output_key: Mapped[str] = mapped_column(String(32), default="report")
    score_output_key: Mapped[str] = mapped_column(String(32), default="score_result")
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, default=60)


class CozeOAuth(Base):
    """租户级 Coze OAuth 连接（客户自助「连接 Coze」）。"""

    __tablename__ = "coze_oauth"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), unique=True)
    client_id: Mapped[str] = mapped_column(String(128))
    client_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 绑定的工作流
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Notification(Base):
    """站内通知。"""

    __tablename__ = "notification"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))  # activation/batch_done/failure
    title: Mapped[str] = mapped_column(String(128))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class JdCategory(Base):
    """岗位分类树节点（docs/07-§4）：dim=industry 为一级行业；dim=function 为职能树
    （一级职能 → 二级细分叶子，岗位挂叶子）。"""

    __tablename__ = "jd_category"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jd_category.id"), nullable=True
    )
    dim: Mapped[str] = mapped_column(String(16))  # industry / function
    name: Mapped[str] = mapped_column(String(64))
    level: Mapped[int] = mapped_column(Integer, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class JdLibrary(Base):
    """公开岗位库（行业-岗位库）：与租户私有 job 表分离，供简历→岗位推荐。"""

    __tablename__ = "jd_library"
    __table_args__ = (
        Index("ix_jdlib_active_cat", "is_active", "category_id"),
        Index("ix_jdlib_industry", "industry_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual/user_submit/api/crawler
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    company: Mapped[str] = mapped_column(String(128))
    industry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jd_category.id"), nullable=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jd_category.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(128))
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    education: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 本科及以上/硕士及以上/不限
    experience_required: Mapped[str | None] = mapped_column(String(32), nullable=True)
    salary_range: Mapped[str | None] = mapped_column(String(64), nullable=True)
    jd_text: Mapped[str] = mapped_column(Text)
    jd_parsed: Mapped[dict | None] = mapped_column(JSONType, nullable=True)  # 技能/证书/硬性条件（结构化）
    quality_score: Mapped[float] = mapped_column(Float, default=1.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    crawl_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class JdSkillOntology(Base):
    """技能本体：规范名 + 同义词（归一化匹配），供技能提取与覆盖率计算。"""

    __tablename__ = "jd_skill_ontology"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    canonical_name: Mapped[str] = mapped_column(String(64), unique=True)
    aliases: Mapped[list | None] = mapped_column(JSONType, nullable=True)  # 同义词/大小写变体
    skill_class: Mapped[str] = mapped_column(String(32), default="tech")  # tech/design/analysis/soft
    is_core_default: Mapped[bool] = mapped_column(Boolean, default=False)


class CertScarcity(Base):
    """证书稀缺度表（docs/07-§6.4）：scarcity_score 1-5，S=5 … C=1。"""

    __tablename__ = "cert_scarcity"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    cert_name: Mapped[str] = mapped_column(String(128), unique=True)
    aliases: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    scarcity_score: Mapped[int] = mapped_column(Integer, default=1)  # 1-5
    level_hint: Mapped[str | None] = mapped_column(String(16), nullable=True)  # S/A/B/C


class ToolchainTemplate(Base):
    """岗位类别的典型工具链清单（技能匹配度-工具链完整度用）。"""

    __tablename__ = "toolchain_template"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jd_category.id"), unique=True)
    toolchain: Mapped[list] = mapped_column(JSONType)  # 规范技能名列表


class Recommendation(Base):
    """简历→岗位推荐记录（C 端，docs/07-§4.2）。"""

    __tablename__ = "recommendation"
    __table_args__ = (Index("ix_reco_tenant_resume", "tenant_id", "resume_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resume.id"))
    jd_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jd_library.id"))
    rank: Mapped[int] = mapped_column(Integer, default=0)
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    hit_skills: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    missing_skills: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_result: Mapped[dict | None] = mapped_column(JSONType, nullable=True)  # 五维评分结果（M7.2）
    status: Mapped[str] = mapped_column(String(16), default="new")  # new/viewed/applied/ignored
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CalibrationFeedback(Base):
    """校准反馈（docs/07-§8.2，M7.3）：HR/求职者对评分的逐维偏差标注。

    回流闭环：周度统计维度偏差率 → 调参（阈值/证书/信号词）→ 评估集回归。
    """

    __tablename__ = "calibration_feedback"
    __table_args__ = (Index("ix_cfb_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="candidate")  # hr / candidate
    target_type: Mapped[str] = mapped_column(String(16), default="recommendation")  # analysis / recommendation
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis.id"), nullable=True)
    resume_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resume.id"), nullable=True)
    jd_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jd_library.id"), nullable=True)
    model_total: Mapped[float | None] = mapped_column(Float, nullable=True)  # 当时模型总分（校准 MAE 用）
    dim_overrated: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    dim_underrated: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    dim_ok: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    agree_interview: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    suggested_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # HR 认可总分（可选）
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CalibrationConfig(Base):
    """校准配置（docs/07-§8.3，M7.3）：评分引擎启动时读取，支持在线调参。

    keys:
      level_thresholds  {"S": 85, "A": 70, "B": 55}
      cert_scarcity     {证书规范名: 1-5 覆盖默认表}
      signal_words      {"industry_cognition": ["行业报告", ...]}
      tier_weights      {档位: {维度: 权重}}（可选覆盖）
    """

    __tablename__ = "calibration_config"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    value: Mapped[dict] = mapped_column(JSONType)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class EvaluationCase(Base):
    """人工标注评估集（docs/07-§8.5，M7.4）：简历 × 岗位 → HR 认可总分/等级。

    用于等级阈值标定（MAE + 阈值扫描寻优）与打分模型蒸馏的训练数据。
    """

    __tablename__ = "evaluation_case"
    __table_args__ = (
        UniqueConstraint("tenant_id", "resume_id", "jd_id", name="uq_eval_resume_jd"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resume.id"))
    jd_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jd_library.id"))
    label_total: Mapped[float] = mapped_column(Float)  # HR 认可总分 0-100
    label_level: Mapped[str | None] = mapped_column(String(8), nullable=True)  # S/A/B/C
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CompanyWatchlist(Base):
    """公司避雷与推荐清单（docs/07-§22，M7.11）。

    kind: blacklist（避雷）/ recommended（高精尖推荐）/ warning（预警，谨慎投递）
    信息来自公开报道与社区投稿，仅供参考；source_url 留痕，可下架。
    """

    __tablename__ = "company_watchlist"
    __table_args__ = (Index("ix_cw_kind_company", "kind", "company"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    company: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16), default="blacklist")  # blacklist/recommended/warning
    industry: Mapped[str | None] = mapped_column(String(64), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(8), nullable=True)  # 高/中/低（blacklist/warning）
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # 避雷原因 / 推荐理由
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)  # 报道/信息来源
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual/user/community
    status: Mapped[str] = mapped_column(String(16), default="active")  # active/removed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Order(Base):
    """套餐订单（M7 收费：线下转账确认 / 预留线上支付回调）。"""

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    plan: Mapped[str] = mapped_column(String(32))  # pro/enterprise
    months: Mapped[int] = mapped_column(Integer, default=1)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)  # 金额（分）
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/paid/cancelled/expired
    pay_method: Mapped[str] = mapped_column(String(16), default="manual")  # manual/wechat/alipay
    trade_no: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 第三方支付单号（预留）
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MpUser(Base):
    """求职端小程序用户（简历罗盘，C 端）：openid 即账号，独立于企业租户。"""

    __tablename__ = "mp_user"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    openid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 免费额度使用标记
    direction_free_used: Mapped[bool] = mapped_column(Boolean, default=False)  # 职业方向匹配免费1次
    job_free_used: Mapped[bool] = mapped_column(Boolean, default=False)  # 岗位匹配报告免费体验1个
    guide_free_used: Mapped[bool] = mapped_column(Boolean, default=False)  # 求职导航免费1次
    # 次数包余额（岗位匹配等每用 1 次扣 1）
    pack_quota: Mapped[int] = mapped_column(Integer, default=0)
    # 最近一次求职分析缓存（方向报告/针对性优化复用，避免重复上传解析）
    last_resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_resume_parsed: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    # 最近一次「方向匹配」会话标识：报告/按方向优化携带该 session 则不再重复扣次（一次匹配=一次完整体验）
    last_dir_session: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 本次方向匹配会话内已生成的免费深度分析用量 {direction_key: {"report": n, "optimize": n}}（成本上限用）
    last_dir_usage: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MpQuotaLog(Base):
    """C 端小程序次数包发放/调整流水（管理员在 Web 后台操作，人工开通阶段的对账依据）。"""

    __tablename__ = "mp_quota_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    mp_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    openid: Mapped[str] = mapped_column(String(64), index=True)
    delta: Mapped[int] = mapped_column(Integer)  # 正=发放；负=扣回
    balance_after: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    operator_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)  # B 端管理员 User.id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
