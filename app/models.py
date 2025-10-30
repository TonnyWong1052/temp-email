from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# 验证码模型
class Code(BaseModel):
    code: str
    type: Literal["numeric", "alphanumeric", "token"]
    length: int
    pattern: str
    confidence: float = Field(ge=0.0, le=1.0)


# 邮件模型
class Mail(BaseModel):
    id: str
    email_token: str
    from_: str = Field(alias="from")
    to: str
    subject: str
    content: str
    html_content: Optional[str] = None
    received_at: datetime
    read: bool = False
    codes: Optional[List[Code]] = None

    class Config:
        populate_by_name = True


# 邮箱模型
class Email(BaseModel):
    token: str
    address: str
    prefix: str
    domain: str
    created_at: datetime
    expires_at: datetime
    mail_count: int = 0


# API响应模型
class ApiResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    message: Optional[str] = None


# 邮箱生成响应
class EmailGenerateResponse(BaseModel):
    success: bool
    data: dict


# 邮件列表响应
class MailListResponse(BaseModel):
    success: bool
    data: dict


# 验证码响应
class CodeResponse(BaseModel):
    success: bool
    data: dict


# 健康检查响应
class HealthResponse(BaseModel):
    success: bool
    status: str
    timestamp: datetime
    uptime: int
    active_emails: int


# 环境配置模型（管理后台使用）
class EnvConfigRequest(BaseModel):
    """环境配置更新请求"""
    # Server
    port: Optional[int] = None
    host: Optional[str] = None
    reload: Optional[bool] = None

    # Custom Domains
    custom_domains: Optional[str] = None
    default_domains: Optional[str] = None
    enable_custom_domains: Optional[bool] = None
    enable_builtin_domains: Optional[bool] = None

    # Cloudflare Workers KV
    use_cloudflare_kv: Optional[bool] = None
    cf_account_id: Optional[str] = None
    cf_kv_namespace_id: Optional[str] = None
    cf_api_token: Optional[str] = None

    # LLM Code Extraction
    use_llm_extraction: Optional[bool] = None
    openai_api_key: Optional[str] = None
    openai_api_base: Optional[str] = None
    openai_model: Optional[str] = None
    default_code_extraction_method: Optional[str] = None  # "llm" or "pattern"

    # Admin Authentication
    admin_username: Optional[str] = None
    admin_password: Optional[str] = None
    admin_secret_key: Optional[str] = None

    # CORS
    cors_origins: Optional[str] = None


class EnvConfigResponse(BaseModel):
    """环境配置响应"""
    success: bool
    config: Optional[dict] = None
    message: Optional[str] = None


# Pattern-based extraction models
class Pattern(BaseModel):
    """用户训练的验证码提取模式"""
    id: str
    keywords_before: List[str]
    keywords_after: List[str]
    code_type: Literal["numeric", "alphanumeric", "token"]
    code_length: int
    regex: str
    example_code: str
    email_content: str  # 完整邮件内容
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)
    created_at: datetime
    usage_count: int = 0
    success_count: int = 0


class LearnPatternRequest(BaseModel):
    """学习新模式的请求"""
    email_content: str
    highlighted_code: str
    highlight_position: int


class LearnPatternResponse(BaseModel):
    """学习模式的响应"""
    success: bool
    pattern_id: Optional[str] = None
    message: str
    preview: Optional[dict] = None


class PatternListResponse(BaseModel):
    """模式列表响应"""
    success: bool
    patterns: List[dict]
    total: int


# 驗證碼提取統計
class CodeExtractionStats(BaseModel):
    """驗證碼提取統計信息"""
    method: str  # 請求的提取方法 (smart, pattern, llm, regex)
    timeMs: float  # 提取耗時（毫秒）
    source: Optional[str] = None  # 實際使用的提取方法
    mailsProcessed: int  # 處理的郵件數量
    codesFound: int  # 找到的驗證碼數量
    extractionMethods: Optional[dict] = None  # 各方法使用次數統計


# 等待新郵件帶驗證碼響應
class WaitWithCodeResponse(BaseModel):
    """等待新郵件（帶自動驗證碼提取）響應"""
    success: bool
    data: dict  # 包含 hasNew, count, mails, extractionStats


# 快速驗證碼 API 響應
class WaitCodeResponse(BaseModel):
    """等待驗證碼（快速 API）響應"""
    success: bool
    data: Optional[dict] = None  # 包含 code, type, confidence, mailId 等
    message: Optional[str] = None  # 超時時的訊息
