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

    async def get_available_models(self, api_base: str = None, api_key: str = None) -> dict:
        """
        從 API 端點獲取可用的模型列表

        Args:
            api_base: API 基礎 URL（可選，默認使用配置中的值）
            api_key: API 密鑰（可選，默認使用配置中的值）

        Returns:
            {
                "success": bool,
                "models": List[str],  # 模型 ID 列表
                "message": str,
                "source": str  # "api" 或 "error"
            }
        """
        base_url = (api_base or self.api_base).rstrip('/')
        key = api_key or self.api_key

        if not key:
            return {
                "success": False,
                "models": [],
                "message": "未配置 API Key",
                "source": "error"
            }

        try:
            await log_service.log(
                level=LogLevel.INFO,
                log_type=LogType.LLM_CALL,
                message=f"正在獲取模型列表",
                details={
                    "api_base": base_url
                }
            )

            # 嘗試調用 /v1/models 端點（OpenAI 標準）
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{base_url}/models",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    }
                )

                if response.status_code == 200:
                    data = response.json()

                    # 解析模型列表（支持多種格式）
                    models = []
                    if isinstance(data, dict):
                        # OpenAI 格式：{"data": [{"id": "gpt-3.5-turbo"}, ...], "object": "list"}
                        if "data" in data and isinstance(data["data"], list):
                            models = [
                                item["id"] if isinstance(item, dict) and "id" in item else str(item)
                                for item in data["data"]
                            ]
                        # 簡單格式：{"models": ["model1", "model2"]}
                        elif "models" in data and isinstance(data["models"], list):
                            models = data["models"]
                        # 其他可能的格式
                        elif "model_list" in data and isinstance(data["model_list"], list):
                            models = data["model_list"]
                    # 直接返回列表
                    elif isinstance(data, list):
                        models = [
                            item["id"] if isinstance(item, dict) and "id" in item else str(item)
                            for item in data
                        ]

                    # 過濾和排序
                    models = [m for m in models if m and isinstance(m, str)]
                    models.sort()

                    await log_service.log(
                        level=LogLevel.SUCCESS,
                        log_type=LogType.LLM_CALL,
                        message=f"成功獲取 {len(models)} 個模型",
                        details={
                            "api_base": base_url,
                            "models_count": len(models)
                        }
                    )

                    return {
                        "success": True,
                        "models": models,
                        "message": f"成功獲取 {len(models)} 個模型",
                        "source": "api"
                    }
                else:
                    error_msg = f"API 返回错误: {response.status_code}"

                    await log_service.log(
                        level=LogLevel.WARNING,
                        log_type=LogType.LLM_CALL,
                        message=error_msg,
                        details={
                            "status_code": response.status_code,
                            "response_text": response.text[:500],
                            "api_base": base_url
                        }
                    )

                    return {
                        "success": False,
                        "models": [],
                        "message": error_msg,
                        "source": "error"
                    }

        except httpx.TimeoutException:
            error_msg = "獲取模型列表超時（10秒）"
            await log_service.log(
                level=LogLevel.WARNING,
                log_type=LogType.LLM_CALL,
                message=error_msg,
                details={
                    "api_base": base_url,
                    "timeout_seconds": 10.0
                }
            )

            return {
                "success": False,
                "models": [],
                "message": error_msg,
                "source": "error"
            }

        except Exception as e:
            error_msg = f"獲取模型列表失敗: {str(e)}"
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.LLM_CALL,
                message=error_msg,
                details={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "api_base": base_url
                }
            )

            return {
                "success": False,
                "models": [],
                "message": error_msg,
                "source": "error"
            }

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
                                "content": "You are a verification code extraction expert. Extract exactly ONE most likely verification code (OTP/PIN/token) from email content. Return JSON array with at most 1 item. If no clear code, return []. No explanations or markdown."
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
        """構建 LLM 提示詞（限定只返回最有把握的一個）"""
        return f"""You are an expert at extracting verification codes from emails. Analyze the following email and extract ONLY the SINGLE MOST LIKELY verification code (OTP/PIN/token). Do not list multiple results.

EMAIL CONTENT:
---
{text[:2000]}
---

SELECTION RULES (choose 1 best):
1. **Numeric codes**: Pure numbers (e.g., 123456, 4567, 87654321)
   - Common lengths: 4, 6, or 8 digits
   - Usually near keywords: "code", "verification", "OTP", "PIN", "驗證碼", "验证码"
   - Prefer 6-digit numeric if equally plausible

2. **Alphanumeric codes**: Mix of letters and numbers (e.g., ABC123, XYZ789)
   - Usually 6-10 characters
   - Often capitalized

3. **Tokens**: Long authentication strings (e.g., eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9)
   - Usually 20+ characters
   - May contain hyphens or underscores
   - Often in URLs or after "token:" keyword
   - Only choose if context explicitly indicates it's the verification code

CONFIDENCE SCORING (for the single choice):
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

OUTPUT CONSTRAINTS:
- Return a JSON array with at most 1 item (0 or 1).
- No markdown or explanations.

SINGLE-ITEM JSON EXAMPLE:
[
  {{
    "code": "123456",
    "type": "numeric",
    "length": 6,
    "confidence": 0.95,
    "context": "verification code is"
  }}
]

If no verification codes found or uncertain, return: []

JSON Response:"""

    def _parse_llm_response(self, content: str) -> List[Code]:
        """解析 LLM 返回的 JSON 響應；若有多個，選擇信心最高的單一結果"""

        # 嘗試提取 JSON 陣列
        json_match = re.search(r'\[[\s\S]*\]', content)
        if not json_match:
            return []

        try:
            data = json.loads(json_match.group())

            # 正常化：確保是列表
            if isinstance(data, dict):
                data = [data]
            if not isinstance(data, list):
                return []

            candidates: List[Code] = []
            seen = set()
            for item in data:
                # 驗證必需字段
                if not isinstance(item, dict) or 'code' not in item:
                    continue

                raw_code = str(item['code']).strip()
                if not raw_code:
                    continue
                # 去重（同一碼只保留一次）
                if raw_code in seen:
                    continue
                seen.add(raw_code)

                code_type = item.get('type', 'alphanumeric')
                if code_type not in ['numeric', 'alphanumeric', 'token']:
                    code_type = 'alphanumeric'

                confidence = float(item.get('confidence', 0.8))
                length = int(item.get('length', len(raw_code)))

                candidates.append(Code(
                    code=raw_code,
                    type=code_type,
                    length=length,
                    pattern='llm_extracted',
                    confidence=confidence
                ))

            if not candidates:
                return []

            # 排序規則：信心值優先，其次偏好數字碼（長度 4-8，特別是 6 位）
            def rank_key(c: Code):
                is_numeric = (c.type == 'numeric') and c.code.isdigit()
                is_len6 = (c.length == 6)
                is_len_4_8 = 4 <= c.length <= 8
                return (
                    -c.confidence,           # 高信心優先
                    -(1 if is_numeric else 0),
                    -(1 if is_len6 else 0),
                    -(1 if is_len_4_8 else 0)
                )

            candidates.sort(key=rank_key)

            # 只返回最優單一結果
            return [candidates[0]]

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
