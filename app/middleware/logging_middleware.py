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
        client_ip = request.client.host if request.client else "unknown"

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

            # 記錄響應
            await log_service.log(
                level=level,
                log_type=LogType.RESPONSE,
                message=f"{method} {path} → {response.status_code}",
                details={
                    "method": method,
                    "path": path,
                    "status_code": response.status_code,
                    "client_ip": client_ip,
                },
                duration_ms=duration_ms
            )

            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            # 記錄錯誤
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.ERROR,
                message=f"{method} {path} → ERROR: {str(e)}",
                details={
                    "method": method,
                    "path": path,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "client_ip": client_ip,
                },
                duration_ms=duration_ms
            )

            raise
