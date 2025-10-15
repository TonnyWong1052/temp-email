"""
Cloudflare Workers KV 郵件服務

從 Cloudflare Workers KV 讀取由 Email Worker 存儲的郵件。
"""

import json
import time
import traceback
from datetime import datetime
from typing import List, Optional, Dict, Any
import httpx

from app.config import settings
from app.models import Mail
from app.services.log_service import log_service, LogLevel, LogType
from app.services.cache_service import mail_index_cache, mail_content_cache


class CloudflareKVClient:
    """Cloudflare Workers KV 客戶端"""

    def __init__(self):
        self._account_id = settings.cf_account_id
        self._namespace_id = settings.cf_kv_namespace_id
        self._api_token = settings.cf_api_token
        self._headers = {}
        self._base_url = ""

        # 初始化 URL 和 headers
        self._update_base_url()
        self._update_headers()

        # 驗證配置
        self._validate_config()

    @property
    def account_id(self):
        """獲取 Account ID"""
        return self._account_id

    @account_id.setter
    def account_id(self, value):
        """設置 Account ID 並自動更新 base_url"""
        self._account_id = value
        self._update_base_url()
        self._validate_config()

    @property
    def namespace_id(self):
        """獲取 Namespace ID"""
        return self._namespace_id

    @namespace_id.setter
    def namespace_id(self, value):
        """設置 Namespace ID 並自動更新 base_url"""
        self._namespace_id = value
        self._update_base_url()
        self._validate_config()

    @property
    def api_token(self):
        """獲取 API Token"""
        return self._api_token

    @api_token.setter
    def api_token(self, value):
        """設置 API Token 並自動更新 headers"""
        self._api_token = value
        self._update_headers()
        self._validate_config()

    @property
    def base_url(self):
        """獲取 Base URL"""
        return self._base_url

    @property
    def headers(self):
        """獲取 Headers"""
        return self._headers

    def _update_base_url(self):
        """更新 Base URL"""
        if self._account_id and self._namespace_id:
            self._base_url = f"https://api.cloudflare.com/client/v4/accounts/{self._account_id}/storage/kv/namespaces/{self._namespace_id}"
        else:
            self._base_url = ""

    def _update_headers(self):
        """更新請求頭"""
        if self._api_token and self._api_token.strip():
            self._headers = {
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/json",
            }
        else:
            self._headers = {
                "Content-Type": "application/json",
            }

    def _validate_config(self):
        """驗證配置完整性"""
        import asyncio

        errors = []
        if not self._account_id or not self._account_id.strip():
            errors.append("CF_ACCOUNT_ID is empty")
        if not self._namespace_id or not self._namespace_id.strip():
            errors.append("CF_NAMESPACE_ID is empty")
        if not self._api_token or not self._api_token.strip():
            errors.append("CF_API_TOKEN is empty")

        if errors:
            # 異步記錄錯誤（不阻塞初始化）
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(log_service.log(
                        level=LogLevel.ERROR,
                        log_type=LogType.KV_ACCESS,
                        message=f"Cloudflare KV configuration incomplete: {', '.join(errors)}",
                        details={"errors": errors}
                    ))
            except Exception:
                # 如果沒有事件循環，使用同步日誌
                import logging
                logging.error(f"Cloudflare KV configuration incomplete: {', '.join(errors)}")

    async def fetch_mails(self, email: str, fetch_full_content: bool = False) -> List[Mail]:
        """
        從 KV 獲取指定郵箱的所有郵件

        Args:
            email: 郵箱地址
            fetch_full_content: 是否獲取完整郵件內容（默認 False，只從索引獲取摘要）

        Returns:
            郵件列表
        """
        start_time = time.time()

        try:
            await log_service.log(
                level=LogLevel.INFO,
                log_type=LogType.KV_ACCESS,
                message=f"Fetching mails for {email} (full_content={fetch_full_content})",
                details={"email": email, "operation": "fetch_mails", "fetch_full_content": fetch_full_content}
            )

            # 首先嘗試從緩存獲取郵件索引
            index_key = f"index:{email}"
            index_data = mail_index_cache.get(index_key)

            if not index_data:
                # 緩存未命中，從 KV 讀取
                index_data = await self._get_kv_value(index_key)
                if index_data:
                    # 存入緩存 (TTL: 30 秒)
                    mail_index_cache.set(index_key, index_data, ttl=30)

            if index_data:
                # 從索引獲取郵件列表
                mail_list = index_data.get("mails", [])
                mails = []

                if fetch_full_content:
                    # 批量獲取完整郵件內容（僅在需要時）
                    for mail_info in mail_list:
                        mail_key = mail_info.get("key")
                        if mail_key:
                            # 先嘗試從緩存獲取
                            mail_data = mail_content_cache.get(mail_key)
                            if not mail_data:
                                # 緩存未命中，從 KV 讀取
                                mail_data = await self._get_kv_value(mail_key)
                                if mail_data:
                                    # 存入緩存 (TTL: 5 分鐘)
                                    mail_content_cache.set(mail_key, mail_data, ttl=300)

                            if mail_data:
                                mail = self._parse_mail_data(mail_data)
                                if mail:
                                    mails.append(mail)
                else:
                    # 直接從索引構建 Mail 對象（優化：減少 KV 讀取）
                    for mail_info in mail_list:
                        mail = self._parse_mail_from_index(mail_info)
                        if mail:
                            mails.append(mail)

                duration_ms = (time.time() - start_time) * 1000
                await log_service.log(
                    level=LogLevel.SUCCESS,
                    log_type=LogType.KV_ACCESS,
                    message=f"Successfully fetched {len(mails)} mails from index (KV reads: {'N+1' if fetch_full_content else '1'})",
                    details={"email": email, "count": len(mails), "method": "index", "kv_reads_optimized": not fetch_full_content},
                    duration_ms=duration_ms
                )

                return mails
            else:
                # 如果沒有索引，使用 prefix 搜索
                return await self._fetch_mails_by_prefix(email)

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.KV_ACCESS,
                message=f"Failed to fetch mails: {str(e)}",
                details={
                    "email": email,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": traceback.format_exc()
                },
                duration_ms=duration_ms
            )
            return []

    async def _fetch_mails_by_prefix(self, email: str) -> List[Mail]:
        """
        通過 prefix 搜索獲取郵件

        Args:
            email: 郵箱地址

        Returns:
            郵件列表
        """
        start_time = time.time()

        try:
            # 列出所有匹配 prefix 的 key
            prefix = f"mail:{email}:"
            keys = await self._list_keys(prefix)

            await log_service.log(
                level=LogLevel.INFO,
                log_type=LogType.KV_ACCESS,
                message=f"Fetching mails by prefix: {prefix}",
                details={"email": email, "prefix": prefix, "keys_found": len(keys)}
            )

            mails = []
            for key_name in keys:
                mail_data = await self._get_kv_value(key_name)
                if mail_data:
                    mail = self._parse_mail_data(mail_data)
                    if mail:
                        mails.append(mail)

            # 按接收時間排序
            mails.sort(key=lambda m: m.received_at, reverse=True)

            duration_ms = (time.time() - start_time) * 1000
            await log_service.log(
                level=LogLevel.SUCCESS,
                log_type=LogType.KV_ACCESS,
                message=f"Successfully fetched {len(mails)} mails by prefix",
                details={"email": email, "count": len(mails), "method": "prefix"},
                duration_ms=duration_ms
            )

            return mails

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.KV_ACCESS,
                message=f"Failed to fetch mails by prefix: {str(e)}",
                details={
                    "email": email,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": traceback.format_exc()
                },
                duration_ms=duration_ms
            )
            return []

    async def _get_kv_value(self, key: str) -> Optional[Dict[str, Any]]:
        """
        從 KV 獲取單個值

        Args:
            key: KV 鍵名

        Returns:
            值（JSON 對象）或 None
        """
        try:
            url = f"{self.base_url}/values/{key}"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=self.headers)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
                else:
                    await log_service.log(
                        level=LogLevel.WARNING,
                        log_type=LogType.KV_ACCESS,
                        message=f"KV GET returned non-200 status: {response.status_code}",
                        details={"key": key, "status_code": response.status_code}
                    )
                    return None

        except Exception as e:
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.KV_ACCESS,
                message=f"Failed to get KV key: {str(e)}",
                details={
                    "key": key,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return None

    async def _list_keys(self, prefix: str, limit: int = 20) -> List[str]:
        """
        列出匹配 prefix 的所有 key

        Args:
            prefix: key 前綴
            limit: 最大返回數量 (優化：從 100 降低到 20)

        Returns:
            key 列表
        """
        try:
            url = f"{self.base_url}/keys"
            params = {"prefix": prefix, "limit": limit}

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=self.headers, params=params)

                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        keys = data.get("result", [])
                        return [k["name"] for k in keys]

            return []

        except Exception as e:
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.KV_ACCESS,
                message=f"Failed to list KV keys: {str(e)}",
                details={
                    "prefix": prefix,
                    "limit": limit,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return []

    def _parse_mail_data(self, data: Dict[str, Any]) -> Optional[Mail]:
        """
        將 KV 數據解析為 Mail 對象

        Args:
            data: KV 中存儲的郵件數據

        Returns:
            Mail 對象或 None
        """
        try:
            # 解析接收時間
            received_at_str = data.get("received_at")
            if received_at_str:
                try:
                    received_at = datetime.fromisoformat(received_at_str.replace("Z", "+00:00"))
                except ValueError:
                    received_at = datetime.now()
            else:
                received_at = datetime.now()

            # 構建 Mail 對象
            mail = Mail(
                id=data.get("id", "unknown"),
                email_token="",  # 將在存儲時設置
                **{
                    "from": data.get("from", "unknown"),
                    "to": data.get("to", ""),
                    "subject": data.get("subject", "(No Subject)"),
                    "content": data.get("content", ""),
                    "html_content": data.get("html_content"),
                    "received_at": received_at,
                    "read": False,
                },
            )

            return mail

        except Exception as e:
            import asyncio
            asyncio.create_task(log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.KV_ACCESS,
                message=f"Failed to parse mail data: {str(e)}",
                details={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "data_keys": list(data.keys()) if isinstance(data, dict) else None
                }
            ))
            return None

    def _parse_mail_from_index(self, mail_info: Dict[str, Any]) -> Optional[Mail]:
        """
        從索引數據構建 Mail 對象（優化版本，無需讀取完整郵件內容）

        Args:
            mail_info: 索引中的郵件摘要信息 (包含 id, from, subject, receivedAt)

        Returns:
            Mail 對象或 None
        """
        try:
            # 解析接收時間
            received_at_str = mail_info.get("receivedAt")
            if received_at_str:
                try:
                    received_at = datetime.fromisoformat(received_at_str.replace("Z", "+00:00"))
                except ValueError:
                    received_at = datetime.now()
            else:
                received_at = datetime.now()

            # 從索引構建簡化的 Mail 對象
            # 注意：content 使用 content_preview（從索引獲取），如需完整內容需再讀取
            content_preview = mail_info.get("content_preview", "")

            mail = Mail(
                id=mail_info.get("id", "unknown"),
                email_token="",  # 將在存儲時設置
                **{
                    "from": mail_info.get("from", "unknown"),
                    "to": mail_info.get("email", ""),  # 索引中沒有 to 字段，使用 email 字段
                    "subject": mail_info.get("subject", "(No Subject)"),
                    "content": content_preview,  # 使用索引中的摘要
                    "html_content": None,
                    "received_at": received_at,
                    "read": False,
                },
            )

            return mail

        except Exception as e:
            import asyncio
            asyncio.create_task(log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.KV_ACCESS,
                message=f"Failed to parse mail from index: {str(e)}",
                details={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "mail_info_keys": list(mail_info.keys()) if isinstance(mail_info, dict) else None
                }
            ))
            return None

    async def test_connection(self) -> bool:
        """
        測試 KV 連接

        Returns:
            是否連接成功
        """
        try:
            url = f"{self.base_url}/keys"
            params = {"limit": 1}

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=self.headers, params=params)
                success = response.status_code == 200

                await log_service.log(
                    level=LogLevel.SUCCESS if success else LogLevel.ERROR,
                    log_type=LogType.KV_ACCESS,
                    message=f"KV connection test: {'success' if success else 'failed'}",
                    details={"status_code": response.status_code}
                )

                return success

        except Exception as e:
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.KV_ACCESS,
                message=f"KV connection test failed: {str(e)}",
                details={
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return False

    async def get_stats(self) -> Dict[str, Any]:
        """
        獲取 KV 統計信息

        Returns:
            統計信息字典
        """
        try:
            # 獲取所有 key（用於統計）
            url = f"{self.base_url}/keys"
            params = {"limit": 1000}

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=self.headers, params=params)

                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        keys = data.get("result", [])

                        # 統計不同類型的 key
                        mail_keys = [k for k in keys if k["name"].startswith("mail:")]
                        index_keys = [k for k in keys if k["name"].startswith("index:")]

                        return {
                            "total_keys": len(keys),
                            "mail_keys": len(mail_keys),
                            "index_keys": len(index_keys),
                            "connected": True,
                        }

            return {"connected": False}

        except Exception as e:
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.KV_ACCESS,
                message=f"Failed to get KV stats: {str(e)}",
                details={
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return {"connected": False, "error": str(e)}


# 單例
kv_client = CloudflareKVClient()
