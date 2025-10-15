import re
from typing import List
from app.models import Code


class CodeService:
    """验证码提取服务"""

    def extract_codes(self, text: str) -> List[Code]:
        """从文本中提取验证码"""
        codes: List[Code] = []

        # 1. 纯数字验证码 (4-8位)
        numeric_patterns = [
            (r"\b\d{6}\b", "numeric", 6, 0.9),
            (r"\b\d{4}\b", "numeric", 4, 0.8),
            (r"\b\d{8}\b", "numeric", 8, 0.85),
        ]

        for pattern, type_, length, confidence in numeric_patterns:
            matches = re.findall(pattern, text)
            for code in matches:
                if not self._is_duplicate(codes, code):
                    codes.append(
                        Code(
                            code=code,
                            type=type_,
                            length=length,
                            pattern=pattern,
                            confidence=confidence,
                        )
                    )

        # 2. 字母數字混合 (6-10位)
        alphanumeric_pattern = r"\b[A-Z0-9]{6,10}\b"
        matches = re.findall(alphanumeric_pattern, text)
        for code in matches:
            if not self._is_duplicate(codes, code):
                codes.append(
                    Code(
                        code=code,
                        type="alphanumeric",
                        length=len(code),
                        pattern=alphanumeric_pattern,
                        confidence=0.75,
                    )
                )

        # 3. 常见验证码关键词附近
        context_patterns = [
            r"(?:code|Code|驗證碼|验证码|OTP|otp)[\s:：]*([A-Z0-9]{4,10})",
            r"(?:your|Your)\s+(?:verification|code)[\s:：]*([A-Z0-9]{4,10})",
            r"(?:token|Token)[\s:：]*([A-Za-z0-9_-]{10,40})",
        ]

        for pattern in context_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for code in matches:
                if not self._is_duplicate(codes, code):
                    type_ = "token" if len(code) > 15 else "alphanumeric"
                    codes.append(
                        Code(
                            code=code,
                            type=type_,
                            length=len(code),
                            pattern=pattern,
                            confidence=0.95,  # 上下文关键词提高置信度
                        )
                    )

        # 4. URL参数中的验证码
        url_pattern = r"[?&](?:code|token|verify)=([A-Za-z0-9_-]+)"
        matches = re.findall(url_pattern, text, re.IGNORECASE)
        for code in matches:
            if not self._is_duplicate(codes, code) and len(code) >= 6:
                type_ = "token" if len(code) > 15 else "alphanumeric"
                codes.append(
                    Code(
                        code=code,
                        type=type_,
                        length=len(code),
                        pattern=url_pattern,
                        confidence=0.85,
                    )
                )

        # 按置信度排序
        return sorted(codes, key=lambda x: x.confidence, reverse=True)

    def _is_duplicate(self, codes: List[Code], code: str) -> bool:
        """检查是否重复"""
        return any(c.code == code for c in codes)

    def extract_from_html(self, html: str) -> List[Code]:
        """从HTML中提取验证码"""
        # 移除HTML标签
        text = re.sub(r"<[^>]*>", " ", html)
        # 解码HTML实体
        text = self._decode_html_entities(text)
        return self.extract_codes(text)

    def _decode_html_entities(self, text: str) -> str:
        """解码HTML实体"""
        import html

        return html.unescape(text)


# 单例
code_service = CodeService()
