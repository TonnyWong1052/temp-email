"""
基於 LLM 的驗證碼提取服務
使用 OpenAI API 來智能提取驗證碼
"""

import json
import re
import time
import traceback
from typing import List, Optional
from app.models import Code
import httpx
from app.config import settings
from app.services.log_service import log_service, LogLevel, LogType


class LLMCodeService:
    """使用 LLM 進行智能驗證碼提取"""

    def __init__(self):
        self.api_key = settings.openai_api_key
        self.api_base = settings.openai_api_base or "https://api.openai.com/v1"
        self.model = settings.openai_model or "gpt-3.5-turbo"
        self.use_llm = settings.use_llm_extraction and bool(self.api_key)

        # 始終初始化回退服務
        from app.services.code_service import code_service
        self.fallback_service = code_service

    async def extract_codes(self, text: str) -> List[Code]:
        """
        從文本中提取驗證碼
        如果 LLM 不可用，回退到正則表達式方法
        """
        if not self.use_llm:
            return self.fallback_service.extract_codes(text)

        try:
            return await self._extract_with_llm(text)
        except Exception as e:
            await log_service.log(
                level=LogLevel.WARNING,
                log_type=LogType.CODE_EXTRACT,
                message=f"LLM extraction failed, falling back to regex: {str(e)}",
                details={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "fallback": "regex"
                }
            )
            return self.fallback_service.extract_codes(text)

    async def _extract_with_llm(self, text: str) -> List[Code]:
        """使用 LLM 提取驗證碼"""
        start_time = time.time()

        # 構建提示詞
        prompt = self._build_prompt(text)

        try:
            await log_service.log(
                level=LogLevel.INFO,
                log_type=LogType.LLM_CALL,
                message=f"Starting LLM code extraction",
                details={
                    "model": self.model,
                    "text_length": len(text),
                    "api_base": self.api_base
                }
            )

            # 調用 OpenAI API
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a verification code extraction expert. Extract verification codes, OTP codes, tokens, and authentication codes from email content. Return results in JSON format only."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.1,  # 低溫度以獲得更確定的結果
                        "max_tokens": 500,
                    }
                )

            if response.status_code != 200:
                error_msg = f"API 調用失敗: {response.status_code} - {response.text}"

                await log_service.log(
                    level=LogLevel.ERROR,
                    log_type=LogType.LLM_CALL,
                    message=error_msg,
                    details={
                        "status_code": response.status_code,
                        "response_text": response.text[:500],
                        "model": self.model
                    }
                )

                raise Exception(error_msg)

            result = response.json()
            content = result["choices"][0]["message"]["content"]

            # 解析 LLM 返回的 JSON
            codes = self._parse_llm_response(content)

            duration_ms = (time.time() - start_time) * 1000
            await log_service.log(
                level=LogLevel.SUCCESS,
                log_type=LogType.LLM_CALL,
                message=f"Successfully extracted {len(codes)} codes with LLM",
                details={
                    "model": self.model,
                    "codes_count": len(codes),
                    "text_length": len(text)
                },
                duration_ms=duration_ms
            )

            return codes

        except httpx.TimeoutException as e:
            duration_ms = (time.time() - start_time) * 1000
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.LLM_CALL,
                message=f"LLM API timeout: {str(e)}",
                details={
                    "error_type": "TimeoutException",
                    "timeout_seconds": 30.0,
                    "model": self.model
                },
                duration_ms=duration_ms
            )
            raise

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.LLM_CALL,
                message=f"LLM extraction error: {str(e)}",
                details={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": traceback.format_exc(),
                    "model": self.model
                },
                duration_ms=duration_ms
            )
            raise

    def _build_prompt(self, text: str) -> str:
        """構建 LLM 提示詞"""
        return f"""You are an expert at extracting verification codes from emails. Analyze the following email and extract ALL verification codes, OTP codes, authentication tokens, or confirmation codes.

EMAIL CONTENT:
---
{text[:2000]}
---

EXTRACTION RULES:
1. **Numeric codes**: Pure numbers (e.g., 123456, 4567, 87654321)
   - Common lengths: 4, 6, or 8 digits
   - Usually near keywords: "code", "verification", "OTP", "PIN", "驗證碼", "验证码"

2. **Alphanumeric codes**: Mix of letters and numbers (e.g., ABC123, XYZ789)
   - Usually 6-10 characters
   - Often capitalized

3. **Tokens**: Long authentication strings (e.g., eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9)
   - Usually 20+ characters
   - May contain hyphens or underscores
   - Often in URLs or after "token:" keyword

CONFIDENCE SCORING:
- 0.95-1.0: Code with explicit keywords (e.g., "Your code is 123456", "驗證碼：123456")
- 0.85-0.94: Code in URL parameters (e.g., ?code=ABC123, &token=xyz)
- 0.80-0.84: Standalone numbers/codes in appropriate context (e.g., email body with verification theme)
- 0.70-0.79: Ambiguous matches that could be codes

AVOID EXTRACTING:
- Years (e.g., 2024, 2025)
- Phone numbers
- Prices or quantities
- Regular English words (e.g., "below", "Hello", "within")
- Dates or times

OUTPUT FORMAT (JSON array only, no markdown or explanations):
[
  {{
    "code": "123456",
    "type": "numeric",
    "length": 6,
    "confidence": 0.95,
    "context": "verification code is"
  }}
]

If no verification codes found, return: []

JSON Response:"""

    def _parse_llm_response(self, content: str) -> List[Code]:
        """解析 LLM 返回的 JSON 響應"""

        # 嘗試提取 JSON 陣列
        json_match = re.search(r'\[[\s\S]*\]', content)
        if not json_match:
            return []

        try:
            data = json.loads(json_match.group())

            codes = []
            for item in data:
                # 驗證必需字段
                if not isinstance(item, dict) or 'code' not in item:
                    continue

                code_type = item.get('type', 'alphanumeric')
                if code_type not in ['numeric', 'alphanumeric', 'token']:
                    code_type = 'alphanumeric'

                codes.append(Code(
                    code=str(item['code']),
                    type=code_type,
                    length=item.get('length', len(str(item['code']))),
                    pattern='llm_extracted',
                    confidence=float(item.get('confidence', 0.8))
                ))

            return codes

        except json.JSONDecodeError as e:
            import asyncio
            asyncio.create_task(log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.CODE_EXTRACT,
                message=f"Failed to parse LLM JSON response: {str(e)}",
                details={
                    "error_type": "JSONDecodeError",
                    "error_message": str(e),
                    "content_preview": content[:500]
                }
            ))
            return []

    async def extract_from_html(self, html: str) -> List[Code]:
        """從 HTML 中提取驗證碼"""
        # 移除 HTML 標籤
        text = re.sub(r"<[^>]*>", " ", html)
        # 解碼 HTML 實體
        text = self._decode_html_entities(text)
        return await self.extract_codes(text)

    def _decode_html_entities(self, text: str) -> str:
        """解碼 HTML 實體"""
        import html
        return html.unescape(text)


# 單例
llm_code_service = LLMCodeService()
