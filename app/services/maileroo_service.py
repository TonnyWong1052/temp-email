import httpx
from typing import Optional, Dict, Any
from app.config import settings
from app.models import Mail
from datetime import datetime


class MailerooService:
    """Maileroo 邮件发送服务"""

    def __init__(self):
        self.api_url = settings.maileroo_api_url
        self.api_key = settings.maileroo_api_key

    async def send_email(
        self,
        to_address: str,
        to_name: Optional[str] = None,
        subject: str = "Test Email",
        html_content: str = "<h1>Test Email</h1><p>This is a test email from Maileroo.</p>",
        from_address: Optional[str] = None,
        from_name: Optional[str] = "Test Service",
    ) -> Dict[str, Any]:
        """
        使用 Maileroo API 发送邮件

        Args:
            to_address: 收件人邮件地址
            to_name: 收件人姓名 (可选)
            subject: 邮件主题
            html_content: HTML 邮件内容
            from_address: 发件人邮件地址 (可选，使用 Maileroo 预设域名)
            from_name: 发件人姓名 (可选)

        Returns:
            API 响应的字典
        """
        if not self.api_key:
            raise ValueError("MAILEROO_API_KEY 未设置")

        # 如果没有指定发件人地址，使用 Maileroo 的预设域名
        if not from_address:
            # 从 API Key 或设置中获取预设域名
            # 这里使用您示例中的域名格式
            from_address = f"no-reply@582717474a02d6a4.maileroo.org"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "from": {
                "address": from_address,
                "display_name": from_name,
            },
            "to": {
                "address": to_address,
                "display_name": to_name or to_address.split("@")[0],
            },
            "subject": subject,
            "html": html_content,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            print(f"Maileroo API 错误: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            print(f"发送邮件时发生错误: {e}")
            raise

    async def send_test_email(self, to_address: str) -> Dict[str, Any]:
        """
        发送测试邮件的便捷方法

        Args:
            to_address: 收件人邮件地址

        Returns:
            API 响应的字典
        """
        timestamp = datetime.now().isoformat()
        subject = f"Test Email from Maileroo - {timestamp}"
        html_content = f"""
        <h1>Test Email</h1>
        <p>This is a test email sent at {timestamp}.</p>
        <p>If you receive this email, the Maileroo integration is working correctly.</p>
        <p>Thank you!</p>
        """

        return await self.send_email(
            to_address=to_address,
            subject=subject,
            html_content=html_content,
            from_name="Maileroo Test Service",
        )


# 单例
maileroo_service = MailerooService()