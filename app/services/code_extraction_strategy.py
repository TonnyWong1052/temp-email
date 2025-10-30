"""
智能驗證碼提取策略服務

實現多層級驗證碼提取策略：
1. Pattern-based (最快，基於用戶訓練的模式)
2. LLM-based (智能，需要 API 調用)
3. Regex-based (兜底，正則表達式)

根據配置和上下文智能選擇最佳提取方法
"""

import time
from typing import List, Optional, Tuple
from app.models import Mail, Code
from app.config import settings


class CodeExtractionStrategy:
    """智能驗證碼提取策略"""

    def __init__(self):
        self._pattern_cache = {}  # 緩存 pattern 匹配結果
        self._stats = {
            "pattern_success": 0,
            "llm_success": 0,
            "regex_success": 0,
            "total_attempts": 0,
        }

    async def extract_codes_smart(
        self, mail: Mail, preferred_method: Optional[str] = None
    ) -> Tuple[List[Code], str, float]:
        """
        智能提取驗證碼（自動選擇最佳方法）

        Args:
            mail: 郵件對象
            preferred_method: 優先使用的方法 ('pattern', 'llm', 'regex', None=auto)

        Returns:
            (codes, method_used, time_ms)
        """
        start_time = time.time()
        self._stats["total_attempts"] += 1

        debug = bool(getattr(settings, "debug_email_fetch", False))

        # 如果指定了特定方法，直接使用
        if preferred_method == "pattern":
            codes, method = await self._extract_with_pattern(mail)
            if codes:
                duration_ms = (time.time() - start_time) * 1000
                return codes, method, duration_ms

        elif preferred_method == "llm":
            codes, method = await self._extract_with_llm(mail)
            if codes:
                duration_ms = (time.time() - start_time) * 1000
                return codes, method, duration_ms

        elif preferred_method == "regex":
            codes, method = await self._extract_with_regex(mail)
            duration_ms = (time.time() - start_time) * 1000
            return codes, method, duration_ms

        # 智能級聯模式（默認）
        if debug:
            print(f"[Code Extraction] Starting smart extraction for mail from {mail.from_}")

        # Step 1: 嘗試 Pattern-based（最快，0 成本）
        codes, method = await self._extract_with_pattern(mail)
        if codes and codes[0].confidence >= 0.85:
            if debug:
                print(f"[Code Extraction] Pattern-based succeeded: {codes[0].code} (confidence: {codes[0].confidence})")
            self._stats["pattern_success"] += 1
            duration_ms = (time.time() - start_time) * 1000
            return codes, method, duration_ms

        # Step 2: 嘗試 LLM-based（智能但有成本）
        if settings.use_llm_extraction:
            codes, method = await self._extract_with_llm(mail)
            if codes and codes[0].confidence >= 0.80:
                if debug:
                    print(f"[Code Extraction] LLM-based succeeded: {codes[0].code} (confidence: {codes[0].confidence})")
                self._stats["llm_success"] += 1
                duration_ms = (time.time() - start_time) * 1000
                return codes, method, duration_ms

        # Step 3: 回退到 Regex-based（兜底）
        codes, method = await self._extract_with_regex(mail)
        if codes:
            if debug:
                print(f"[Code Extraction] Regex-based succeeded: {codes[0].code} (confidence: {codes[0].confidence})")
            self._stats["regex_success"] += 1

        duration_ms = (time.time() - start_time) * 1000
        return codes, method, duration_ms

    async def _extract_with_pattern(self, mail: Mail) -> Tuple[List[Code], str]:
        """使用 Pattern-based 提取"""
        try:
            from app.services.pattern_code_service import pattern_code_service

            # 先從純文本提取
            codes = pattern_code_service.extract_codes(mail.content or "")

            # 如果沒找到且有 HTML，從 HTML 提取
            if not codes and mail.html_content:
                codes = pattern_code_service.extract_from_html(mail.html_content)

            return codes, "pattern"
        except Exception as e:
            debug = bool(getattr(settings, "debug_email_fetch", False))
            if debug:
                print(f"[Code Extraction] Pattern extraction error: {e}")
            return [], "pattern"

    async def _extract_with_llm(self, mail: Mail) -> Tuple[List[Code], str]:
        """使用 LLM-based 提取"""
        try:
            from app.services.llm_code_service import llm_code_service

            # 先從純文本提取
            codes = await llm_code_service.extract_codes(mail.content or "")

            # 如果沒找到且有 HTML，從 HTML 提取
            if not codes and mail.html_content:
                codes = await llm_code_service.extract_from_html(mail.html_content)

            return codes, "llm"
        except Exception as e:
            debug = bool(getattr(settings, "debug_email_fetch", False))
            if debug:
                print(f"[Code Extraction] LLM extraction error: {e}")
            return [], "llm"

    async def _extract_with_regex(self, mail: Mail) -> Tuple[List[Code], str]:
        """使用 Regex-based 提取"""
        try:
            from app.services.code_service import code_service

            # 先從純文本提取
            codes = code_service.extract_codes(mail.content or "")

            # 如果沒找到且有 HTML，從 HTML 提取
            if not codes and mail.html_content:
                codes = code_service.extract_from_html(mail.html_content)

            return codes, "regex"
        except Exception as e:
            debug = bool(getattr(settings, "debug_email_fetch", False))
            if debug:
                print(f"[Code Extraction] Regex extraction error: {e}")
            return [], "regex"

    def get_stats(self) -> dict:
        """獲取提取統計"""
        return {
            **self._stats,
            "success_rate": (
                (self._stats["pattern_success"] + self._stats["llm_success"] + self._stats["regex_success"])
                / max(self._stats["total_attempts"], 1)
            ),
        }


# 單例
code_extraction_strategy = CodeExtractionStrategy()
