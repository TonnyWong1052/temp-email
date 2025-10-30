import asyncio
import time
import traceback
from datetime import datetime
from typing import List, Tuple
import httpx
import ftfy
from app.config import settings
from app.models import Mail
from urllib.parse import quote
from email.utils import parsedate_to_datetime
from app.services.log_service import log_service, LogLevel, LogType


class MailService:
    """邮件接收服务 - 支持多种邮件来源 + 智能緩存"""

    async def fetch_mails(self, email: str, force_refresh: bool = False) -> List[Mail]:
        """
        從郵箱獲取郵件（智能路由 + 智能緩存）

        ⚡️ 性能優化核心：
        1. L1 緩存（30秒）- 高頻訪問直接返回，響應時間 <100ms
        2. L2 緩存（5分鐘）- API 失敗時降級兜底
        3. 請求合併 - 避免並發重複調用
        4. 智能路由 - 按域名選擇最佳郵件源

        根據郵箱域名自動選擇郵件來源：
        - 自定義域名（在 CF_KV_DOMAINS 中）→ Cloudflare Workers KV
        - 內建域名（20個 pp.ua, gravityengine.cc 等）→ 外部 API (mail.chatgpt.org.uk)

        Args:
            email: 郵箱地址
            force_refresh: 強制刷新緩存（跳過 L1 緩存）

        Returns:
            郵件列表
        """
        debug = bool(getattr(settings, "debug_email_fetch", False))

        if debug:
            print(f"[Mail Service] fetch_mails() called for: {email}, force_refresh={force_refresh}")

        # 如果 Redis 已啟用，使用智能緩存層
        if settings.enable_redis:
            try:
                from app.services.cache_manager import cache_manager

                # 使用緩存管理器（帶降級保護）
                mails, from_cache = await cache_manager.get_or_fetch_mails(
                    email=email,
                    fetch_func=self._fetch_mails_without_cache,
                    force_refresh=force_refresh
                )

                if debug:
                    cache_status = "HIT" if from_cache else "MISS"
                    print(f"[Mail Service] Cache {cache_status}: {len(mails)} mails")

                return mails

            except Exception as e:
                # 緩存層失敗時降級到直接獲取
                if debug:
                    print(f"[Mail Service] Cache layer failed, falling back to direct fetch: {e}")

        # Redis 未啟用或緩存失敗 → 直接獲取
        return await self._fetch_mails_without_cache(email)

    async def _fetch_mails_without_cache(self, email: str) -> List[Mail]:
        """
        直接從源獲取郵件（無緩存）

        此方法被 cache_manager 調用，或在 Redis 未啟用時使用
        """
        debug = bool(getattr(settings, "debug_email_fetch", False))

        # 智能判断使用哪个来源
        from app.config import should_use_cloudflare_kv

        use_kv = should_use_cloudflare_kv(email)

        if debug:
            domain = email.split('@')[1] if '@' in email else 'unknown'
            source = "Cloudflare KV" if use_kv else "External API (mail.chatgpt.org.uk)"
            print(f"[Mail Service] Domain: {domain} → Source: {source}")

        # 根据智能路由结果选择邮件来源
        if use_kv:
            mails = await self._fetch_from_cloudflare_kv(email)
            if debug:
                print(f"[Mail Service] Cloudflare KV returned {len(mails)} mails")
            return mails
        else:
            mails = await self._fetch_from_external_api(email)
            if debug:
                print(f"[Mail Service] External API returned {len(mails)} mails")
                for i, mail in enumerate(mails, 1):
                    print(f"[Mail Service]   Mail #{i}: from={mail.from_}, subject={mail.subject[:50]}")
            return mails

    async def _fetch_from_cloudflare_kv(self, email: str) -> List[Mail]:
        """从 Cloudflare Workers KV 获取邮件"""
        start_time = time.time()
        debug = bool(getattr(settings, "debug_email_fetch", False))

        try:
            await log_service.log(
                level=LogLevel.INFO,
                log_type=LogType.KV_ACCESS,
                message=f"Fetching mails from Cloudflare KV: {email}",
                details={"email": email, "source": "cloudflare_kv"}
            )

            from app.services.kv_mail_service import kv_client

            mails = await kv_client.fetch_mails(email)

            duration_ms = (time.time() - start_time) * 1000
            await log_service.log(
                level=LogLevel.SUCCESS,
                log_type=LogType.EMAIL_FETCH,
                message=f"Successfully fetched {len(mails)} mails from Cloudflare KV",
                details={"email": email, "count": len(mails), "source": "cloudflare_kv"},
                duration_ms=duration_ms
            )

            # 不自动提取验证码，由用户按需提取
            # mails = await self._extract_codes_for_mails(mails)

            return mails

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.EMAIL_FETCH,
                message=f"Failed to fetch mails from Cloudflare KV: {str(e)}",
                details={
                    "email": email,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": traceback.format_exc() if debug else None,
                    "source": "cloudflare_kv"
                },
                duration_ms=duration_ms
            )
            return []

    async def _fetch_external_api_reliable(self, url: str, debug: bool, ssl_verify: bool) -> List[Mail]:
        """
        可靠模式 - 外部 API 獲取（帶重試機制）
        特點：HTTP 超時 30 秒 + 自動重試 3 次 + 穩定的錯誤處理
        """
        timeout_seconds = float(getattr(settings, "email_request_timeout", 30.0))
        retry_times = int(getattr(settings, "email_retry_times", 3))

        for attempt in range(retry_times):
            try:
                if debug:
                    print(f"[Mail Service][Reliable Mode] Attempt {attempt + 1}/{retry_times}")
                    print(f"[Mail Service][Reliable Mode] GET {url}")

                await log_service.log(
                    level=LogLevel.INFO,
                    log_type=LogType.EMAIL_FETCH,
                    message=f"External API (Reliable): Attempt {attempt + 1}/{retry_times}",
                    details={"url": url, "timeout": timeout_seconds, "ssl_verify": ssl_verify}
                )

                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                }

                async with httpx.AsyncClient(timeout=timeout_seconds, verify=ssl_verify) as client:
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()

                    data = response.json()

                    if debug:
                        import json as json_lib
                        print(f"[Mail Service][Reliable Mode] Response: {json_lib.dumps(data, indent=2, ensure_ascii=False)[:500]}...")

                    # 標準的 emails 陣列解析邏輯
                    if isinstance(data, dict) and "emails" in data:
                        emails_array = data["emails"]
                        if isinstance(emails_array, list):
                            mails: List[Mail] = []

                            for email_data in emails_array:
                                if not isinstance(email_data, dict):
                                    continue

                                # 提取標準字段
                                from_addr = self._fix_encoding(email_data.get("from", ""))
                                subject = self._fix_encoding(email_data.get("subject", "(No Subject)"))
                                content = self._fix_encoding(email_data.get("content", ""))

                                # 获取 HTML 内容 (支持多种字段名)
                                html_content = (
                                    email_data.get("html")
                                    or email_data.get("htmlContent")  # 实际 API 使用的字段
                                    or email_data.get("html_content")
                                )

                                # 获取日期 (优先使用 timestamp 毫秒时间戳)
                                date_value = email_data.get("timestamp") or email_data.get("date")
                                received_at = self._parse_date(date_value) if date_value else datetime.now()

                                # 生成稳定 ID
                                content_preview = content[:100] if content else ""
                                # 注意: 这里需要邮箱地址,从 URL 提取
                                email_address = url.split("email=")[-1].split("&")[0] if "email=" in url else "unknown"
                                from urllib.parse import unquote
                                email_address = unquote(email_address)

                                mail_id = self._generate_stable_mail_id(
                                    email_address, from_addr, subject, received_at, content_preview
                                )

                                mail = Mail(
                                    id=mail_id,
                                    email_token="",
                                    **{
                                        "from": from_addr,
                                        "to": email_address,
                                        "subject": subject,
                                        "content": content,
                                        "html_content": html_content,
                                        "received_at": received_at,
                                        "read": False,
                                    },
                                )
                                mails.append(mail)

                            if debug:
                                print(f"[Mail Service][Reliable Mode] Found {len(mails)} mails")

                            await log_service.log(
                                level=LogLevel.SUCCESS,
                                log_type=LogType.EMAIL_FETCH,
                                message=f"External API (Reliable): Successfully fetched {len(mails)} mails",
                                details={"url": url, "count": len(mails), "attempt": attempt + 1}
                            )

                            return mails

                    if debug:
                        print(f"[Mail Service][Reliable Mode] No emails found in response")
                    return []

            except httpx.TimeoutException as e:
                if debug:
                    print(f"[Mail Service][Reliable Mode] Timeout on attempt {attempt + 1}: {e}")

                await log_service.log(
                    level=LogLevel.WARNING,
                    log_type=LogType.EMAIL_FETCH,
                    message=f"External API (Reliable): Timeout on attempt {attempt + 1}/{retry_times}",
                    details={
                        "url": url,
                        "error_type": "TimeoutException",
                        "error_message": str(e),
                        "attempt": attempt + 1,
                        "retry_times": retry_times
                    }
                )

                if attempt < retry_times - 1:
                    await asyncio.sleep(2)  # 重试前等待2秒
                    continue
                else:
                    await log_service.log(
                        level=LogLevel.ERROR,
                        log_type=LogType.EMAIL_FETCH,
                        message=f"External API (Reliable): All {retry_times} attempts failed (timeout)",
                        details={"url": url, "error_type": "TimeoutException"}
                    )
                    raise

            except Exception as e:
                if debug:
                    import traceback
                    print(f"[Mail Service][Reliable Mode] Error on attempt {attempt + 1}: {e}")
                    print(f"[Mail Service][Reliable Mode] Traceback:\n{traceback.format_exc()}")

                await log_service.log(
                    level=LogLevel.WARNING if attempt < retry_times - 1 else LogLevel.ERROR,
                    log_type=LogType.EMAIL_FETCH,
                    message=f"External API (Reliable): Error on attempt {attempt + 1}/{retry_times}",
                    details={
                        "url": url,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "traceback": traceback.format_exc() if debug else None,
                        "attempt": attempt + 1,
                        "retry_times": retry_times
                    }
                )

                if attempt < retry_times - 1:
                    await asyncio.sleep(2)
                    continue
                else:
                    raise

        return []

    async def _fetch_from_external_api(self, email: str) -> List[Mail]:
        """从外部API获取邮件（支持兼容模式）"""
        start_time = time.time()
        debug = bool(getattr(settings, "debug_email_fetch", False))

        try:
            base = getattr(settings, "email_api_url", "https://mail.chatgpt.org.uk/api/get-emails").rstrip("?&")
            url = f"{base}{'&' if '?' in base else '?'}email={quote(email)}"
            compat = getattr(settings, "email_compat_mode", None)
            ssl_verify = bool(getattr(settings, "email_api_ssl_verify", True))

            if debug:
                print(f"[Mail Service] _fetch_from_external_api() URL: {url}")
                print(f"[Mail Service] Compat mode: {compat}, SSL verify: {ssl_verify}, Debug: {debug}")

            await log_service.log(
                level=LogLevel.INFO,
                log_type=LogType.EMAIL_FETCH,
                message=f"Fetching mails from external API: {email}",
                details={
                    "email": email,
                    "url": url,
                    "compat_mode": compat,
                    "ssl_verify": ssl_verify,
                    "source": "external_api"
                }
            )

            # 使用可靠模式（帶重試機制）
            if compat == "reliable":
                if debug:
                    print(f"[Mail Service] Using Reliable mode (with retry)")
                return await self._fetch_external_api_reliable(url, debug, ssl_verify)

            if compat == "enhanced":
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                }
            else:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json",
                }

            if debug:
                print(f"[Mail Service][DEBUG] GET {url} verify={ssl_verify} compat={compat}")

            async with httpx.AsyncClient(timeout=10.0, verify=ssl_verify) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

                data = response.json()

                # 调试模式：记录完整响应结构
                if debug:
                    import json as json_lib
                    print(f"[Mail Service][DEBUG] Response data: {json_lib.dumps(data, indent=2, ensure_ascii=False)[:500]}...")

                # 如果启用增強模式，優先嚴格解析 {"emails": [...]}
                # 修复：只有在真正找到邮件时才返回，否则继续通用解析
                if compat == "enhanced" and isinstance(data, dict) and isinstance(data.get("emails"), list):
                    raw = data.get("emails")
                    mails: List[Mail] = []
                    for email_data in raw:
                        if not isinstance(email_data, dict):
                            continue
                        content = email_data.get("content") or ""
                        html_content = (
                            email_data.get("html")
                            or email_data.get("html_content")
                            or email_data.get("htmlContent")
                            or None
                        )
                        if not content and html_content:
                            content = self._extract_text_from_html(html_content)

                        # 修復編碼問題
                        content = self._fix_encoding(content)

                        received_at = self._parse_date(email_data.get("date"))
                        from_addr = self._fix_encoding(email_data.get("from", "unknown"))
                        subject = self._fix_encoding(email_data.get("subject", "(No Subject)"))
                        content_preview = content[:100] if content else ""
                        mail_id = self._generate_stable_mail_id(
                            email, from_addr, subject, received_at, content_preview
                        )
                        mails.append(
                            Mail(
                                id=mail_id,
                                email_token="",
                                **{
                                    "from": from_addr,
                                    "to": email,
                                    "subject": subject,
                                    "content": content,
                                    "html_content": html_content,
                                    "received_at": received_at,
                                    "read": False,
                                },
                            )
                        )
                    # 修复：只有在真正找到邮件时才提前返回
                    if mails:
                        if debug:
                            print(f"[Mail Service][DEBUG] Enhanced mode found {len(mails)} mails")
                        return mails
                    else:
                        if debug:
                            print(f"[Mail Service][DEBUG] Enhanced mode: no mails found, falling back to generic parsing")

                # 通用解析（回退）
                raw = None
                if isinstance(data, dict):
                    raw = data.get("emails")
                    if raw is None:
                        d = data.get("data")
                        if isinstance(d, dict):
                            raw = d.get("emails") or d.get("mails")
                        elif isinstance(d, list):
                            raw = d
                elif isinstance(data, list):
                    raw = data

                if not raw:
                    return []

                mails: List[Mail] = []
                for email_data in raw:
                    if not isinstance(email_data, dict):
                        continue

                    content = (
                        email_data.get("content")
                        or email_data.get("body")
                        or email_data.get("text")
                        or email_data.get("message")
                        or ""
                    )
                    html_content = (
                        email_data.get("html")
                        or email_data.get("html_content")
                        or email_data.get("htmlContent")
                        or email_data.get("body_html")
                        or None
                    )
                    if not content and html_content:
                        content = self._extract_text_from_html(html_content)

                    # 修復編碼問題
                    content = self._fix_encoding(content)

                    # 优先使用 timestamp (实际 API 返回的毫秒时间戳)
                    dtv = (
                        email_data.get("timestamp")  # 提高优先级 (毫秒时间戳)
                        or email_data.get("date")
                        or email_data.get("receivedAt")
                        or email_data.get("time")
                        or email_data.get("ts")
                    )
                    received_at = self._parse_date(dtv)

                    from_addr = self._fix_encoding(email_data.get("from", "unknown"))
                    subject = self._fix_encoding(email_data.get("subject", "(No Subject)"))
                    content_preview = content[:100] if content else ""
                    mail_id = self._generate_stable_mail_id(
                        email, from_addr, subject, received_at, content_preview
                    )

                    mail = Mail(
                        id=mail_id,
                        email_token="",
                        **{
                            "from": from_addr,
                            "to": email,
                            "subject": subject,
                            "content": content,
                            "html_content": html_content,
                            "received_at": received_at,
                            "read": False,
                        },
                    )
                    mails.append(mail)

                return mails

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            # 统一记录错误到日志服务 (不区分 debug 模式)
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.EMAIL_FETCH,
                message=f"Failed to fetch mails from external API: {str(e)}",
                details={
                    "email": email,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": traceback.format_exc(),
                    "source": "external_api",
                    "compat_mode": getattr(settings, "email_compat_mode", None)
                },
                duration_ms=duration_ms
            )

            # 保留 debug 模式的 print 输出 (向后兼容)
            if debug:
                print(f"[Mail Service][DEBUG] Fetch error: {e}")
                print(f"[Mail Service][DEBUG] Traceback:\n{traceback.format_exc()}")

            return []

    async def _extract_codes_for_mails(self, mails: List[Mail]) -> List[Mail]:
        """
        为邮件列表提取验证码
        根据配置使用 LLM 或正则表达式方法
        """
        if settings.use_llm_extraction:
            # 使用 LLM 提取
            from app.services.llm_code_service import llm_code_service

            for mail in mails:
                codes = await llm_code_service.extract_codes(mail.content)
                if not codes and mail.html_content:
                    # 如果纯文本没有验证码，尝试从HTML提取
                    codes = await llm_code_service.extract_from_html(mail.html_content)
                if codes:
                    mail.codes = codes
        else:
            # 使用正则表达式提取
            from app.services.code_service import code_service

            for mail in mails:
                codes = code_service.extract_codes(mail.content)
                if not codes and mail.html_content:
                    # 如果纯文本没有验证码，尝试从HTML提取
                    codes = code_service.extract_from_html(mail.html_content)
                if codes:
                    mail.codes = codes

        return mails

    async def wait_for_new_mail(
        self, email: str, since_date: datetime, timeout: int = 30
    ) -> List[Mail]:
        """等待新邮件 (轮询)"""
        start_time = asyncio.get_event_loop().time()
        try:
            check_interval = max(1, int(getattr(settings, "mail_check_interval", 5)))
        except Exception:
            check_interval = 5
        timeout_seconds = timeout

        while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
            mails = await self.fetch_mails(email)

            # 过滤出新邮件
            new_mails = [m for m in mails if m.received_at > since_date]

            if new_mails:
                return new_mails

            # 等待后再检查
            await asyncio.sleep(check_interval)

        return []  # 超时，无新邮件

    async def wait_for_new_mail_with_codes(
        self,
        email: str,
        since_date: datetime,
        timeout: int = 30,
        extraction_method: str = "smart",
        min_confidence: float = 0.8,
    ) -> Tuple[List[Mail], dict]:
        """
        等待新郵件並自動提取驗證碼（增強版）

        Args:
            email: 郵箱地址
            since_date: 只返回此時間後的郵件
            timeout: 超時時間（秒）
            extraction_method: 提取方法 ('smart', 'pattern', 'llm', 'regex')
            min_confidence: 最小置信度過濾

        Returns:
            (mails_with_codes, extraction_stats)
        """
        from app.services.code_extraction_strategy import code_extraction_strategy

        debug = bool(getattr(settings, "debug_email_fetch", False))
        extraction_start = time.time()

        # 等待新郵件
        new_mails = await self.wait_for_new_mail(email, since_date, timeout)

        if not new_mails:
            return [], {
                "method": extraction_method,
                "timeMs": 0,
                "source": None,
                "mailsProcessed": 0,
                "codesFound": 0,
            }

        if debug:
            print(f"[Mail Service] Found {len(new_mails)} new mails, extracting codes...")

        # 為每封郵件提取驗證碼
        extraction_sources = []
        total_codes_found = 0

        for mail in new_mails:
            # 根據指定方法提取
            preferred = None if extraction_method == "smart" else extraction_method
            codes, method_used, duration_ms = await code_extraction_strategy.extract_codes_smart(
                mail, preferred_method=preferred
            )

            # 過濾低置信度的驗證碼
            if codes:
                filtered_codes = [c for c in codes if c.confidence >= min_confidence]
                mail.codes = filtered_codes
                total_codes_found += len(filtered_codes)
                extraction_sources.append(method_used)

                if debug and filtered_codes:
                    print(
                        f"[Mail Service] Mail {mail.id}: Found {len(filtered_codes)} codes "
                        f"(method: {method_used}, time: {duration_ms:.0f}ms)"
                    )

        extraction_duration = (time.time() - extraction_start) * 1000

        # 統計信息
        stats = {
            "method": extraction_method,
            "timeMs": round(extraction_duration, 2),
            "source": extraction_sources[0] if extraction_sources else None,
            "mailsProcessed": len(new_mails),
            "codesFound": total_codes_found,
            "extractionMethods": dict(
                (method, extraction_sources.count(method)) for method in set(extraction_sources)
            )
            if extraction_sources
            else {},
        }

        return new_mails, stats

    def _parse_date(self, v) -> datetime:
        """解析多种日期格式"""
        try:
            if isinstance(v, (int, float)):
                ts = float(v)
                ts = ts / 1000.0 if ts > 1e11 else ts
                return datetime.fromtimestamp(ts)
            if isinstance(v, str):
                s = v.strip()
                if s.endswith("Z"):
                    s = s.replace("Z", "+00:00")
                try:
                    return datetime.fromisoformat(s)
                except Exception:
                    pass
                try:
                    dt = parsedate_to_datetime(v)
                    if dt:
                        return dt
                except Exception:
                    pass
        except Exception:
            pass
        return datetime.now()

    def _generate_stable_mail_id(
        self, to: str, from_addr: str, subject: str, received_at: datetime, content_preview: str = ""
    ) -> str:
        """生成稳定的邮件ID - 基于邮件内容而非时间戳"""
        import hashlib

        # 完全基于内容生成ID，不依赖时间
        # 这样即使API每次返回的时间略有不同，ID也保持一致
        unique_string = f"{to}:{from_addr}:{subject}:{content_preview}"
        hash_value = hashlib.md5(unique_string.encode()).hexdigest()[:16]
        return f"mail_{hash_value}"

    def extract_urls(self, content: str) -> List[str]:
        """从邮件内容中查找URL"""
        import re

        url_regex = r"https?://[^\s<>\"']+"
        return re.findall(url_regex, content)

    def format_as_text(self, mail: Mail) -> str:
        """格式化邮件为纯文本"""
        return f"""From: {mail.from_}
To: {mail.to}
Subject: {mail.subject}
Date: {mail.received_at.isoformat()}

{mail.content}"""

    def _extract_text_from_html(self, html: str) -> str:
        """从HTML中提取纯文本（改進版：正確處理空白字符）"""
        import re

        # 移除script和style标签
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # 步驟 1: 為塊級元素添加換行符（確保內容分段）
        # 這些標籤通常代表內容的邏輯分隔，應該保留為換行
        block_elements = ['p', 'div', 'br', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                          'li', 'tr', 'td', 'th', 'blockquote', 'pre']
        for tag in block_elements:
            # 閉合標籤後添加換行
            html = re.sub(rf'</{tag}>', f'</{tag}>\n', html, flags=re.IGNORECASE)
            # <br> 和 <hr> 可能是自閉合
            if tag in ['br', 'hr']:
                html = re.sub(rf'<{tag}[^>]*/?>', f'<{tag}>\n', html, flags=re.IGNORECASE)

        # 步驟 2: 為行內元素之間添加空格（避免單詞連接）
        # 在所有剩餘的標籤前後添加空格
        html = re.sub(r'<([^>]+)>', r' <\1> ', html)

        # 步驟 3: 移除所有HTML标签（此時已有適當的空白字符）
        text = re.sub(r'<[^>]+>', '', html)

        # 步驟 4: 解码HTML实体
        import html as html_module
        text = html_module.unescape(text)

        # 步驟 5: 清理多余空白（但保留換行）
        # 先將多個空格合併為一個空格
        text = re.sub(r'[ \t]+', ' ', text)
        # 清理多餘換行（最多保留兩個連續換行）
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        # 移除每行前後的空白
        text = '\n'.join(line.strip() for line in text.split('\n'))
        # 移除文首文尾的空白
        text = text.strip()

        return text

    def _fix_encoding(self, text: str) -> str:
        """
        修復可能的編碼問題

        使用 ftfy 自動檢測並修復常見的編碼問題：
        - Mojibake（文字化け）：錯誤編碼導致的亂碼
        - 混合編碼問題（如 GB2312/GBK/Big5 被當作 UTF-8 解析）
        - HTML entities 解碼
        - Unicode 規範化
        """
        if not text:
            return text

        try:
            # 使用 ftfy 自動修復編碼問題
            # fix_text() 會自動檢測常見的編碼問題並修復
            fixed = ftfy.fix_text(text)
            return fixed
        except Exception as e:
            # 修復失敗時，返回原文本（避免崩潰）
            debug = bool(getattr(settings, "debug_email_fetch", False))
            if debug:
                print(f"[Mail Service] Encoding fix failed: {e}")
            return text


# 單例
mail_service = MailService()
