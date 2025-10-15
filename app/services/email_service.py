import secrets
import re
from datetime import datetime, timedelta
from typing import Optional
from app.config import get_active_domains, get_default_domain, parse_domain_list, settings
from app.models import Email


class EmailService:
    """郵箱生成服務"""

    def generate_email(self, prefix: str = None, domain: str = None) -> Email:
        """
        生成隨機郵箱

        Args:
            prefix: 自定義前綴（可選）
            domain: 指定域名（可選，需在可用列表中）

        Returns:
            Email: 生成的郵箱對象

        Raises:
            ValueError: 如果指定的域名不在可用列表中
        """
        token = self._generate_token()
        email_prefix = prefix or self._generate_random_prefix()

        # 驗證並選擇域名
        if domain:
            if not self.validate_domain(domain):
                raise ValueError(f"Domain '{domain}' is not in the available domains list")
            email_domain = domain
        else:
            email_domain = self._select_random_domain()

        address = f"{email_prefix}@{email_domain}"

        now = datetime.now()
        expires_at = now + timedelta(hours=1)  # 1小時後過期

        return Email(
            token=token,
            address=address,
            prefix=email_prefix,
            domain=email_domain,
            created_at=now,
            expires_at=expires_at,
            mail_count=0,
        )

    def _generate_token(self) -> str:
        """生成唯一Token (32字符十六進制)"""
        return secrets.token_hex(16)

    def _generate_random_prefix(self) -> str:
        """生成隨機郵箱前綴 (12字符十六進制)"""
        return secrets.token_hex(6)

    def _select_random_domain(self) -> str:
        """
        隨機選擇一個域名（所有域名均等機率）

        從所有可用域名中真正隨機選擇，確保每個域名都有相等的選擇機率
        """
        active_domains = get_active_domains()
        return secrets.choice(active_domains)

    def validate_domain(self, domain: str) -> bool:
        """
        驗證域名是否在可用列表中

        Args:
            domain: 要驗證的域名

        Returns:
            bool: 域名是否有效
        """
        active_domains = get_active_domains()
        return domain in active_domains

    def get_available_domains(self) -> list[str]:
        """獲取所有可用域名列表"""
        return get_active_domains()

    def get_domain_info(self) -> dict:
        """
        獲取域名配置信息

        Returns:
            dict: 包含域名來源和統計信息
        """
        active = get_active_domains()
        custom = parse_domain_list(settings.custom_domains) if settings.custom_domains else []
        default = get_default_domain()

        return {
            "total": len(active),
            "custom_count": len(custom),
            "default_domain": default,
            "has_custom": settings.enable_custom_domains and len(custom) > 0,
            "has_builtin": settings.enable_builtin_domains,
        }

    def validate_email(self, email: str) -> bool:
        """驗證郵箱格式"""
        pattern = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
        return bool(re.match(pattern, email))

    def is_expired(self, email: Email) -> bool:
        """檢查郵箱是否過期"""
        return datetime.now() > email.expires_at

    def get_email_web_url(self, email: str) -> Optional[str]:
        """
        生成郵箱Web URL

        如果使用 Cloudflare KV，則不返回外部 URL（返回 None）
        否則返回外部郵件查看 URL
        """
        # 如果使用 Cloudflare KV，不返回外部 URL
        if settings.use_cloudflare_kv:
            return None

        from urllib.parse import quote
        return f"https://mail.chatgpt.org.uk?email={quote(email)}"


# 單例
email_service = EmailService()
