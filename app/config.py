import os
import json
from typing import List, Optional, Union
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    port: int = 1234
    host: str = "0.0.0.0"
    reload: bool = True

    # Redis（高流量支持）
    redis_url: str = "redis://localhost:6379/0"  # Redis 連接 URL
    enable_redis: bool = False  # 啟用 Redis 分布式存儲（需要先安裝 Redis）
    cache_ttl: int = 30  # 緩存刷新間隔（秒）
    cache_max_size: int = 10000  # 最大緩存條目數

    # 流量控制配置
    rate_limit_enabled: bool = True  # 啟用 API 限流
    rate_limit_per_minute: int = 60  # 每個 IP 每分鐘最大請求數
    circuit_breaker_enabled: bool = True  # 啟用斷路器（API 失敗時自動降級）
    circuit_breaker_threshold: int = 5  # 連續失敗次數閾值
    circuit_breaker_timeout: int = 60  # 斷路器恢復時間（秒）

    # Email
    email_api_url: str = "https://mail.chatgpt.org.uk/api/get-emails"
    email_ttl: int = 3600
    mail_check_interval: int = 10  # 优化：从 5 秒增加到 10 秒，减少轮询频率
    max_mails_per_email: int = 50
    # External inbox compatibility & diagnostics
    email_compat_mode: Optional[str] = None  # "enhanced" for strict parsing, "reliable" for retry mechanism
    email_api_ssl_verify: bool = True  # allow disabling SSL verification for troubleshooting only
    debug_email_fetch: bool = False  # verbose logs and enable debug endpoint
    email_request_timeout: float = 30.0  # HTTP request timeout in seconds (default: 30s)
    email_retry_times: int = 3  # number of retries on failure (default: 3)

    # Custom Domains
    custom_domains: Optional[str] = None  # JSON array string
    default_domains: Optional[str] = None  # JSON array string
    enable_custom_domains: bool = False
    enable_builtin_domains: bool = True

    # Cloudflare Workers KV (Email Workers 整合)
    use_cloudflare_kv: bool = False  # 启用 Cloudflare KV 作为邮件来源
    cf_kv_domains: Optional[str] = None  # 指定哪些域名使用 KV (JSON array)，为空时所有域名使用 KV
    cf_account_id: str = ""  # Cloudflare 帐户 ID
    cf_kv_namespace_id: str = ""  # Workers KV namespace ID
    cf_api_token: str = ""  # Cloudflare API Token

    # LLM Code Extraction (智能验证码提取)
    use_llm_extraction: bool = True  # 启用 LLM 提取验证码
    openai_api_key: str = ""  # 从环境变量加载，默认留空避免泄露
    openai_api_base: Optional[str] = "https://api.longcat.chat/openai/v1"  # OpenAI API Base URL
    openai_model: str = "LongCat-Flash-Chat"  # 使用的模型
    default_code_extraction_method: str = "llm"  # 默认验证码提取方法: "llm" 或 "pattern"

    # Admin Authentication (管理员认证)
    admin_username: str = "admin"  # 管理员用户名
    admin_password: str = "admin123"  # 管理员密码
    admin_secret_key: str = "your-secret-key-here-change-in-production"  # JWT 密钥
    
    # JWT Configuration
    jwt_algorithm: str = "HS256"  # JWT 签名算法
    jwt_access_token_expire_minutes: int = 1440  # JWT 过期时间（分钟），默认 24 小时

    # Logging
    enable_file_logging: bool = True  # 启用文件日志
    log_file_path: str = "logs"  # 日志文件目录
    log_retention_days: int = 7  # 日志保留天数
    log_max_file_size_mb: int = 10  # 单个日志文件最大大小（MB）
    # Maileroo Email Sending Service
    maileroo_api_url: str = "https://smtp.maileroo.com/api/v2/emails"
    maileroo_api_key: str = ""  # 从环境变量加载

    # CORS（容错：支持 JSON 数组、逗号分隔字符串或单个 *）
    cors_origins: Union[List[str], str] = ["*"]

    class Config:
        env_file = ".env"


settings = Settings()

# 内置的邮箱域名（作为后备选项）
BUILTIN_EMAIL_DOMAINS = [
    "chatgptuk.pp.ua",
    "freemails.pp.ua",
    "email.gravityengine.cc",
    "gravityengine.cc",
    "3littlemiracles.com",
    "almiswelfare.org",
    "gyan-netra.com",
    "iraniandsa.org",
    "14club.org.uk",
    "aard.org.uk",
    "allumhall.co.uk",
    "cade.org.uk",
    "caye.org.uk",
    "cketrust.org",
    "club106.org.uk",
    "cok.org.uk",
    "cwetg.co.uk",
    "goleudy.org.uk",
    "hhe.org.uk",
    "hottchurch.org.uk",
]


def parse_domain_list(json_str: Optional[str]) -> List[str]:
    """解析域名列表 JSON 字符串"""
    if not json_str:
        return []
    try:
        domains = json.loads(json_str)
        if isinstance(domains, list):
            return [d.strip() for d in domains if isinstance(d, str) and d.strip()]
        return []
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Failed to parse domain list: {e}")
        return []


def get_active_domains() -> List[str]:
    """
    获取当前活跃的域名列表

    合并策略：
    1. 如果启用自定义域名且有配置，使用自定义域名
    2. 如果允许使用内置域名，添加内置域名
    3. 去重并保持顺序
    """
    domains = []

    # 添加自定义域名
    if settings.enable_custom_domains and settings.custom_domains:
        custom = parse_domain_list(settings.custom_domains)
        domains.extend(custom)

    # 添加内置域名
    if settings.enable_builtin_domains:
        domains.extend(BUILTIN_EMAIL_DOMAINS)

    # 去重保持顺序
    seen = set()
    unique_domains = []
    for domain in domains:
        if domain not in seen:
            seen.add(domain)
            unique_domains.append(domain)

    return unique_domains if unique_domains else BUILTIN_EMAIL_DOMAINS


def get_default_domain() -> Optional[str]:
    """获取默认优先域名"""
    if settings.default_domains:
        defaults = parse_domain_list(settings.default_domains)
        if defaults:
            return defaults[0]

    active = get_active_domains()
    return active[0] if active else None


# 向后兼容：保持 EMAIL_DOMAINS 变量
EMAIL_DOMAINS = get_active_domains()


def get_cors_origins_list() -> List[str]:
    """将 settings.cors_origins 解析为字符串列表，容错处理部署环境中非 JSON 的情况。"""
    v = getattr(settings, "cors_origins", ["*"])
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        s = v.strip()
        if s == "*" or s in ('"*"', "'*'"):
            return ["*"]
        # 优先尝试 JSON 解析
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
            if isinstance(parsed, str):
                return [parsed]
        except Exception:
            pass
        # 回退到逗号分隔
        parts = [p.strip().strip('"').strip("'") for p in s.split(",") if p.strip()]
        if parts:
            return parts
    # 默认允许所有
    return ["*"]


def get_kv_domains() -> List[str]:
    """获取使用 Cloudflare KV 的域名列表"""
    if settings.cf_kv_domains:
        domains = parse_domain_list(settings.cf_kv_domains)
        # 标准化域名（转小写）
        return [d.lower() for d in domains]
    return []


def should_use_cloudflare_kv(email: str) -> bool:
    """
    根据邮箱域名判断是否使用 Cloudflare KV

    智能路由逻辑（已优化）：
    1. 如果全局未启用 KV → 返回 False（所有域名使用外部 API）
    2. 如果启用 KV 但未指定 cf_kv_domains：
       a. 如果有自定义域名 → 只对自定义域名使用 KV（自动绑定）
       b. 否则 → 所有域名使用 KV（向后兼容）
    3. 如果指定了 cf_kv_domains → 检查邮箱域名是否在列表中

    Args:
        email: 邮箱地址，例如 "test@leungchushing.best"

    Returns:
        True: 使用 Cloudflare KV
        False: 使用外部 API (mail.chatgpt.org.uk)

    Examples:
        >>> should_use_cloudflare_kv("test@leungchushing.best")
        True  # 如果自定义域名包含 "leungchushing.best"

        >>> should_use_cloudflare_kv("test@chatgptuk.pp.ua")
        False  # 内建域名使用外部 API
    """
    # 全局未启用 KV
    if not settings.use_cloudflare_kv:
        return False

    # 获取 KV 域名列表
    kv_domains = get_kv_domains()

    # 如果没有指定 CF_KV_DOMAINS，自动绑定到自定义域名
    if not kv_domains:
        # 如果启用了自定义域名，只对自定义域名使用 KV
        if settings.enable_custom_domains and settings.custom_domains:
            kv_domains = parse_domain_list(settings.custom_domains)
            # 标准化域名（转小写）
            kv_domains = [d.lower() for d in kv_domains]
        else:
            # 没有自定义域名，向后兼容：所有域名使用 KV
            return True

    # 提取邮箱域名并标准化
    try:
        domain = email.split('@')[1].lower().strip()
        return domain in kv_domains
    except (IndexError, AttributeError):
        # 无效邮箱格式，预设不使用 KV
        return False
