"""应用配置：从环境变量 / .env 读取，全部可覆盖。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ResumeMatch API"
    debug: bool = False

    # 数据库 / 缓存
    database_url: str = "postgresql+asyncpg://resume:resume@localhost:5432/resume_saas"
    redis_url: str = "redis://localhost:6379/0"

    # Coze 对接（可选的备用引擎；主引擎见下方 DeepSeek）
    coze_base_url: str = "https://api.coze.cn"
    coze_api_token: str = ""
    coze_workflow_id: str = ""
    coze_file_input_key: str = "resume_file"
    coze_jd_input_key: str = "jd_text"
    coze_report_output_key: str = "report"
    coze_score_output_key: str = "score_result"
    coze_rate_limit_rpm: int = 60
    coze_poll_interval: float = 3.0
    coze_poll_max_wait: float = 1800.0

    # 自研引擎：DeepSeek（主引擎，OpenAI 兼容接口）
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # 模拟模式：不配置 COZE_API_TOKEN/COZE_WORKFLOW_ID 时，适配器返回模拟报告，
    # 便于在拿到凭证/发布工作流之前联调全链路。
    mock_mode: bool = True

    # 对外访问地址（OAuth 回调、前端静态托管等用）
    public_base_url: str = "http://127.0.0.1:8000"

    # Coze OAuth（客户自助连接）
    coze_oauth_enc_key: str = ""  # Fernet key（base64），为空则开发默认 key
    coze_oauth_www_url: str = "https://www.coze.cn"
    coze_oauth_token_url: str = "https://api.coze.cn/api/permission/oauth/token"

    cors_origins: list[str] = ["http://localhost:5173"]

    # 认证与多租户（M5）
    jwt_secret: str = "dev-only-secret-change-in-production"
    jwt_expire_days: int = 7
    # 套餐与定价（M7 收费）：quota -1 = 不限；price_month 单位元
    plan_pricing: dict[str, dict] = {
        "free": {"name": "免费版", "price_month": 0, "quota": 50, "desc": "体验基础功能"},
        "pro": {"name": "专业版", "price_month": 99, "quota": 500, "desc": "适合中小团队招聘"},
        "enterprise": {"name": "企业版", "price_month": 299, "quota": -1, "desc": "不限量+多语言深度分析"},
    }
    # 线下转账信息（支付渠道可插拔：manual 现用，wechat/alipay 资质齐全后接入）
    billing_contact: str = "联系销售开通：demo@resume-match.com"
    billing_payee: str = "转账至对公账户（示例）：XX科技有限公司 6222 0000 0000 0000"

    # 求职端小程序「简历罗盘」（C 端，个人主体）
    wx_appid: str = "wx3d09f84d9f829852"
    wx_secret: str = ""  # 未配置 → 开发模式：wx.login code 直接映射 openid，配好 Secret 后自动切真实登录
    mp_token_expire_days: int = 30
    # C 端次数包定价（元）
    mp_pack_pricing: dict[str, dict] = {
        "1x": {"count": 1, "price": 9.9},
        "10x": {"count": 10, "price": 69},
        "50x": {"count": 50, "price": 299},
    }

    # 简历原件存储目录
    upload_dir: str = "data/uploads"

    # M7.4 向量精排（可选）：fastembed + BAAI/bge-small-zh-v1.5（ONNX，无需 torch）。
    # 未启用或模型不可用时，推荐流水线自动回退 TF-IDF 余弦相似度。
    vector_rerank_enabled: bool = False
    vector_rerank_model: str = "BAAI/bge-small-zh-v1.5"
    vector_rerank_weight: float = 0.5  # 最终相似度 = w×向量 + (1-w)×TF-IDF

    # SMTP 邮件（生产化）：激活/通知邮件发送
    smtp_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 465  # 465=SSL / 587=STARTTLS
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""  # 发件人邮箱（为空时用 smtp_user）
    smtp_from_name: str = "ResumeMatch"
    smtp_tls: str = "ssl"  # ssl / starttls / none
    smtp_timeout: int = 15

    @property
    def coze_configured(self) -> bool:
        return bool(self.coze_api_token and self.coze_workflow_id)

    @property
    def llm_configured(self) -> bool:
        return bool(self.deepseek_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
