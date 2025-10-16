"""
FastAPI 日誌中間件
自動記錄所有 HTTP 請求和響應
"""

import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from app.services.log_service import log_service, LogLevel, LogType
import json
from typing import Optional
import traceback


async def get_request_body(request: Request) -> Optional[str]:
    """
    安全地讀取請求 body（不影響後續處理）
    只讀取 JSON 和文本內容，限制大小避免內存問題
    """
    try:
        content_type = request.headers.get("content-type", "")

        # 只處理 JSON 和文本類型
        if not any(ct in content_type.lower() for ct in ["application/json", "text/", "application/x-www-form-urlencoded"]):
            return None

        # 讀取 body（限制大小：100KB）
        body_bytes = await request.body()
        if len(body_bytes) > 100 * 1024:  # 100KB
            return f"<Body too large: {len(body_bytes)} bytes>"

        # 解碼為文本
        body_text = body_bytes.decode("utf-8")

        # 嘗試格式化 JSON
        if "application/json" in content_type:
            try:
                body_json = json.loads(body_text)
                return json.dumps(body_json, indent=2, ensure_ascii=False)
            except:
                pass

        return body_text[:1000]  # 最多返回 1000 字符
    except Exception as e:
        return f"<Error reading body: {str(e)}>"


def get_client_ip(request: Request) -> str:
    """
    獲取客戶端真實 IP 地址
    優先從 HTTP 頭中提取（適用於反向代理環境）

    優先級順序：
    1. X-Forwarded-For（Nginx、Cloudflare 等）
    2. X-Real-IP（Nginx）
    3. CF-Connecting-IP（Cloudflare專用）
    4. request.client.host（直接連接）
    """
    # 1. X-Forwarded-For（可能包含多個 IP，取第一個）
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For 格式：client, proxy1, proxy2
        # 取第一個（最原始的客戶端 IP）
        return forwarded_for.split(",")[0].strip()

    # 2. X-Real-IP（Nginx 常用）
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # 3. CF-Connecting-IP（Cloudflare 專用）
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    # 4. 直接連接的 IP（兜底）
    if request.client:
        return request.client.host

    return "unknown"


class LoggingMiddleware(BaseHTTPMiddleware):
    """HTTP 請求/響應日誌中間件"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        # 不記錄日誌的路徑（避免日誌風暴）
        self.skip_paths = {
            "/admin/logs/stream",  # SSE 端點
            "/docs",
            "/redoc",
            "/openapi.json",
            "/static",
        }

    async def dispatch(self, request: Request, call_next):
        """處理請求並記錄日誌"""

        # 跳過特定路徑
        if any(request.url.path.startswith(path) for path in self.skip_paths):
            return await call_next(request)

        # 記錄請求開始時間
        start_time = time.time()

        # 提取請求信息
        method = request.method
        path = request.url.path
        query_params = dict(request.query_params)
        client_ip = get_client_ip(request)  # 使用新的 IP 提取函數

        # 保存原始 request body（用於錯誤時記錄）
        request_body = None

        # 記錄請求
        await log_service.log(
            level=LogLevel.INFO,
            log_type=LogType.REQUEST,
            message=f"{method} {path}",
            details={
                "method": method,
                "path": path,
                "query": query_params,
                "client_ip": client_ip,
            }
        )

        # 處理請求
        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000

            # 判斷響應級別
            if response.status_code >= 500:
                level = LogLevel.ERROR
            elif response.status_code >= 400:
                level = LogLevel.WARNING
            elif response.status_code >= 300:
                level = LogLevel.INFO
            else:
                level = LogLevel.SUCCESS

            # 準備響應詳情
            response_details = {
                "method": method,
                "path": path,
                "status_code": response.status_code,
                "client_ip": client_ip,
            }

            # 如果是錯誤響應，記錄請求 body 和響應頭
            if response.status_code >= 400:
                # 讀取請求 body（需要重新構造 request 讀取）
                try:
                    # 注意：此時 request body 可能已被消費，需要從原始 scope 重新構造
                    # 這裡簡化處理，只記錄headers
                    response_details["request_headers"] = dict(request.headers)
                    response_details["request_query"] = query_params

                    # 記錄響應頭
                    response_details["response_headers"] = dict(response.headers)

                    # 如果有異常信息，從響應頭或其他地方提取
                    if response.status_code >= 500:
                        response_details["error_hint"] = "Server internal error - check server logs for details"
                    elif response.status_code == 404:
                        response_details["error_hint"] = "Resource not found"
                    elif response.status_code == 401:
                        response_details["error_hint"] = "Unauthorized access"
                    elif response.status_code == 403:
                        response_details["error_hint"] = "Forbidden"
                    elif response.status_code == 422:
                        response_details["error_hint"] = "Validation error - check request parameters"
                    else:
                        response_details["error_hint"] = f"Client error: {response.status_code}"

                except Exception as detail_error:
                    response_details["detail_extraction_error"] = str(detail_error)

            # 記錄響應
            await log_service.log(
                level=level,
                log_type=LogType.RESPONSE,
                message=f"{method} {path} → {response.status_code}",
                details=response_details,
                duration_ms=duration_ms
            )

            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            # 獲取完整錯誤堆棧
            error_traceback = traceback.format_exc()

            # 記錄錯誤（包含詳細信息）
            error_details = {
                "method": method,
                "path": path,
                "error": str(e),
                "error_type": type(e).__name__,
                "client_ip": client_ip,
                "traceback": error_traceback,
                "request_headers": dict(request.headers),
                "request_query": query_params,
            }

            # 嘗試讀取請求 body
            try:
                # 創建新的 Request 對象來讀取 body
                from starlette.requests import Request as StarletteRequest
                body_text = await get_request_body(request)
                if body_text:
                    error_details["request_body"] = body_text
            except Exception as body_error:
                error_details["request_body"] = f"<Error reading body: {str(body_error)}>"

            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.ERROR,
                message=f"{method} {path} → ERROR: {str(e)}",
                details=error_details,
                duration_ms=duration_ms
            )

            raise
