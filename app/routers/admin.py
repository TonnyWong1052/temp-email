"""
管理後台 API 路由
支援登入驗證和完整 .env 配置管理
"""

from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Cookie, Query, status, Response, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import hashlib
import secrets
import asyncio
from app.config import settings
from app.models import EnvConfigRequest, EnvConfigResponse
from app.services.env_service import env_service
from app.services.log_service import log_service, LogLevel, LogType
from app.services.auth_service import auth_service
from app.services.cloudflare_helper import cloudflare_helper
import os
import re

router = APIRouter(prefix="/admin", tags=["Admin"])

# JWT Bearer 認證（允許缺少 Authorization 以便使用 Cookie 作為後備）
security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    token: Optional[str] = None
    token_type: Optional[str] = None
    expires_in: Optional[int] = None


class LLMConfigRequest(BaseModel):
    use_llm_extraction: bool
    openai_api_key: str
    openai_api_base: str
    openai_model: str


class LLMConfigResponse(BaseModel):
    success: bool
    config: dict
    message: Optional[str] = None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session_token: Optional[str] = Cookie(default=None)
) -> str:
    """
    獲取當前認證用戶的依賴項
    
    Args:
        credentials: HTTP Bearer 認證憑證
        
    Returns:
        用戶名
        
    Raises:
        HTTPException: 如果認證失敗
    """
    token: Optional[str] = None

    # 優先使用 Authorization Bearer，其次使用 Cookie
    if credentials and getattr(credentials, "credentials", None):
        token = credentials.credentials
    elif session_token:
        token = session_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供認證憑證"
        )

    username = auth_service.get_current_user_from_token(token)
    return username


@router.post("/login", response_model=LoginResponse)
async def admin_login(request: LoginRequest, response: Response):
    """
    管理員登入
    驗證用戶名和密碼，返回 JWT token
    """
    # 驗證用戶憑證
    if auth_service.authenticate_user(request.username, request.password):
        # 創建 JWT token
        access_token = auth_service.create_user_token(request.username)

        # 設置 HttpOnly Cookie，供前端頁面（如 logs.html 的 SSE）使用
        response.set_cookie(
            key="session_token",
            value=access_token,
            httponly=True,
            max_age=settings.jwt_access_token_expire_minutes * 60,
            samesite="lax",
            secure=False,
            path="/",
        )

        return LoginResponse(
            success=True,
            message="登入成功",
            token=access_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60  # 轉換為秒
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用戶名或密碼錯誤"
        )


@router.post("/logout")
async def admin_logout(response: Response, current_user: str = Depends(get_current_user)):
    """管理員登出（JWT 無狀態，客戶端刪除 token 即可）"""
    # 刪除會話 Cookie
    response.delete_cookie(key="session_token", path="/")
    return {"success": True, "message": "登出成功"}


@router.get("/config/llm", response_model=LLMConfigResponse)
async def get_llm_config(current_user: str = Depends(get_current_user)):
    """
    獲取 LLM 配置
    需要登入
    """
    config = {
        "use_llm_extraction": settings.use_llm_extraction,
        "openai_api_key": settings.openai_api_key,
        "openai_api_base": settings.openai_api_base or "https://api.openai.com/v1",
        "openai_model": settings.openai_model,
    }

    return LLMConfigResponse(success=True, config=config)


@router.post("/config/llm", response_model=LLMConfigResponse)
async def update_llm_config(
    request: LLMConfigRequest, current_user: str = Depends(get_current_user)
):
    """
    更新 LLM 配置
    需要登入
    """

    try:
        # 更新配置（運行時）
        settings.use_llm_extraction = request.use_llm_extraction
        settings.openai_api_key = request.openai_api_key
        settings.openai_api_base = request.openai_api_base
        settings.openai_model = request.openai_model

        # 重新初始化 LLM 服務
        from app.services.llm_code_service import llm_code_service

        llm_code_service.api_key = request.openai_api_key
        llm_code_service.api_base = request.openai_api_base
        llm_code_service.model = request.openai_model
        llm_code_service.use_llm = request.use_llm_extraction and bool(
            request.openai_api_key
        )

        config = {
            "use_llm_extraction": settings.use_llm_extraction,
            "openai_api_key": settings.openai_api_key,
            "openai_api_base": settings.openai_api_base,
            "openai_model": settings.openai_model,
        }

        return LLMConfigResponse(success=True, config=config, message="配置更新成功")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"配置更新失敗: {str(e)}")


class LLMModelsRequest(BaseModel):
    """獲取 LLM 模型列表請求"""
    openai_api_base: Optional[str] = None
    openai_api_key: Optional[str] = None


@router.post("/llm/models")
async def get_llm_models(
    request: LLMModelsRequest,
    current_user: str = Depends(get_current_user)
):
    """
    獲取 LLM API 提供的模型列表
    需要登入

    Args:
        request: 包含 API Base 和 API Key（可選，優先使用請求參數，否則使用配置）

    Returns:
        {
            "success": bool,
            "models": List[str],  # 模型 ID 列表
            "message": str,
            "source": str  # "api" 或 "error"
        }
    """
    try:
        from app.services.llm_code_service import llm_code_service

        # 優先使用請求參數，否則使用當前配置
        api_base = request.openai_api_base or settings.openai_api_base
        api_key = request.openai_api_key or settings.openai_api_key

        if not api_key:
            return {
                "success": False,
                "models": [],
                "message": "請先配置 OpenAI API Key",
                "source": "error"
            }

        if not api_base:
            return {
                "success": False,
                "models": [],
                "message": "請先配置 API Base URL",
                "source": "error"
            }

        # 調用服務獲取模型列表
        result = await llm_code_service.get_available_models(
            api_base=api_base,
            api_key=api_key
        )

        return result

    except Exception as e:
        return {
            "success": False,
            "models": [],
            "message": f"獲取模型列表失敗: {str(e)}",
            "source": "error"
        }


@router.get("/verify")
async def verify_session_endpoint(current_user: str = Depends(get_current_user)):
    """驗證 JWT 是否有效"""
    return {"success": True, "authenticated": True, "user": current_user}


@router.get("/whoami")
async def whoami(request: Request, current_user: str = Depends(get_current_user)):
    """取得當前用戶與請求資訊（IP / User-Agent）"""
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    return {"success": True, "user": current_user, "ip": ip, "user_agent": ua}


@router.get("/debug/config")
async def debug_config(current_user: str = Depends(get_current_user)):
    """
    診斷配置狀態
    顯示環境變數加載情況，幫助診斷 Docker 環境配置問題
    需要登入
    """
    def safe_len(value):
        """安全獲取長度，處理 None 和空值"""
        if value is None:
            return 0
        return len(str(value).strip())

    def is_empty(value):
        """檢查是否為空"""
        if value is None:
            return True
        return not str(value).strip()

    # Cloudflare KV 配置診斷
    cf_config = {
        "use_cloudflare_kv": settings.use_cloudflare_kv,
        "cf_account_id": {
            "length": safe_len(settings.cf_account_id),
            "is_empty": is_empty(settings.cf_account_id),
            "value_preview": settings.cf_account_id[:8] + "..." if settings.cf_account_id and len(settings.cf_account_id) > 8 else settings.cf_account_id or "(empty)"
        },
        "cf_kv_namespace_id": {
            "length": safe_len(settings.cf_kv_namespace_id),
            "is_empty": is_empty(settings.cf_kv_namespace_id),
            "value_preview": settings.cf_kv_namespace_id[:8] + "..." if settings.cf_kv_namespace_id and len(settings.cf_kv_namespace_id) > 8 else settings.cf_kv_namespace_id or "(empty)"
        },
        "cf_api_token": {
            "length": safe_len(settings.cf_api_token),
            "is_empty": is_empty(settings.cf_api_token),
            "value_preview": settings.cf_api_token[:8] + "..." if settings.cf_api_token and len(settings.cf_api_token) > 8 else "(empty)"
        },
        "cf_kv_domains": {
            "value": settings.cf_kv_domains,
            "is_empty": is_empty(settings.cf_kv_domains)
        }
    }

    # 域名配置診斷
    domain_config = {
        "enable_custom_domains": settings.enable_custom_domains,
        "custom_domains": {
            "value": settings.custom_domains,
            "is_empty": is_empty(settings.custom_domains)
        },
        "default_domains": {
            "value": settings.default_domains,
            "is_empty": is_empty(settings.default_domains)
        },
        "enable_builtin_domains": settings.enable_builtin_domains
    }

    # LLM 配置診斷
    llm_config = {
        "use_llm_extraction": settings.use_llm_extraction,
        "openai_api_key": {
            "length": safe_len(settings.openai_api_key),
            "is_empty": is_empty(settings.openai_api_key),
            "value_preview": settings.openai_api_key[:8] + "..." if settings.openai_api_key and len(settings.openai_api_key) > 8 else "(empty)"
        },
        "openai_api_base": settings.openai_api_base,
        "openai_model": settings.openai_model
    }

    # 配置完整性檢查
    config_issues = []
    if settings.use_cloudflare_kv:
        if is_empty(settings.cf_account_id):
            config_issues.append("CF_ACCOUNT_ID is empty")
        if is_empty(settings.cf_kv_namespace_id):
            config_issues.append("CF_KV_NAMESPACE_ID is empty")
        if is_empty(settings.cf_api_token):
            config_issues.append("CF_API_TOKEN is empty")

    if settings.use_llm_extraction and is_empty(settings.openai_api_key):
        config_issues.append("OPENAI_API_KEY is empty but LLM extraction is enabled")

    return {
        "success": True,
        "cloudflare_kv": cf_config,
        "domains": domain_config,
        "llm": llm_config,
        "issues": config_issues,
        "has_issues": len(config_issues) > 0,
        "message": "⚠️ 發現配置問題" if config_issues else "✅ 配置正常"
    }


@router.get("/", response_class=HTMLResponse)
async def admin_page():
    """
    管理後台首頁
    返回 HTML 頁面
    """
    with open("static/admin.html", "r", encoding="utf-8") as f:
        return f.read()


@router.get("/logs.html", response_class=HTMLResponse)
async def admin_logs_page():
    """日誌監控頁面 HTML"""
    with open("static/logs.html", "r", encoding="utf-8") as f:
        return f.read()


@router.get("/config/env", response_model=EnvConfigResponse)
async def get_env_config(current_user: str = Depends(get_current_user)):
    """
    獲取完整的 .env 配置
    需要登入
    """

    try:
        # 從 .env 檔案讀取配置
        env_data = env_service.read_env()

        # 組織配置為結構化格式
        config = {
            "server": {
                "port": env_data.get("PORT", str(settings.port)),
                "host": env_data.get("HOST", settings.host),
                "reload": env_data.get("RELOAD", str(settings.reload).lower()),
            },
            "domains": {
                "custom_domains": env_data.get("CUSTOM_DOMAINS", settings.custom_domains or ""),
                "default_domains": env_data.get("DEFAULT_DOMAINS", settings.default_domains or ""),
                "enable_custom_domains": env_data.get("ENABLE_CUSTOM_DOMAINS", str(settings.enable_custom_domains).lower()),
                "enable_builtin_domains": env_data.get("ENABLE_BUILTIN_DOMAINS", str(settings.enable_builtin_domains).lower()),
            },
            "cloudflare": {
                "use_cloudflare_kv": env_data.get("USE_CLOUDFLARE_KV", str(settings.use_cloudflare_kv).lower()),
                "cf_account_id": env_data.get("CF_ACCOUNT_ID", settings.cf_account_id),
                "cf_kv_namespace_id": env_data.get("CF_KV_NAMESPACE_ID", settings.cf_kv_namespace_id),
                "cf_api_token": env_data.get("CF_API_TOKEN", settings.cf_api_token),
            },
            "llm": {
                "use_llm_extraction": env_data.get("USE_LLM_EXTRACTION", str(settings.use_llm_extraction).lower()),
                "openai_api_key": env_data.get("OPENAI_API_KEY", settings.openai_api_key),
                "openai_api_base": env_data.get("OPENAI_API_BASE", settings.openai_api_base or ""),
                "openai_model": env_data.get("OPENAI_MODEL", settings.openai_model),
                "default_code_extraction_method": env_data.get("DEFAULT_CODE_EXTRACTION_METHOD", settings.default_code_extraction_method),
            },
            "admin": {
                "admin_username": env_data.get("ADMIN_USERNAME", settings.admin_username),
                "admin_password": env_data.get("ADMIN_PASSWORD", "******"),  # 隱藏密碼
                "admin_secret_key": env_data.get("ADMIN_SECRET_KEY", "******"),  # 隱藏密鑰
            },
            "cors": {
                "cors_origins": env_data.get("CORS_ORIGINS", str(settings.cors_origins)),
            },
        }

        return EnvConfigResponse(success=True, config=config)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取配置失敗: {str(e)}")


@router.post("/config/env", response_model=EnvConfigResponse)
async def update_env_config(
    request: EnvConfigRequest, current_user: str = Depends(get_current_user)
):
    """
    更新 .env 配置並保存到檔案
    需要登入
    """

    try:
        # 創建備份
        env_service.backup_env()

        # 準備更新的配置項（只更新非 None 的值）
        updates = {}

        # 將 Pydantic 模型轉換為字典，過濾 None 值
        request_dict = request.model_dump(exclude_none=True)

        # 轉換為環境變數格式（大寫 + 下劃線）
        for key, value in request_dict.items():
            env_key = key.upper()
            updates[env_key] = value

        # 驗證配置
        is_valid, error_msg = env_service.validate_config(updates)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

        # 更新 .env 檔案
        success = env_service.update_env(updates)

        if not success:
            raise HTTPException(status_code=500, detail="寫入配置檔案失敗")

        # 更新運行時配置
        _update_runtime_settings(request_dict)

        # 區分可熱重載的配置和需要重啟的配置
        hot_reloadable = {
            "use_llm_extraction", "openai_api_key", "openai_api_base", "openai_model", 
            "default_code_extraction_method",
            "use_cloudflare_kv", "cf_account_id", "cf_kv_namespace_id", "cf_api_token",
            "custom_domains", "default_domains", "enable_custom_domains", "enable_builtin_domains",
            "email_ttl", "mail_check_interval", "max_mails_per_email",
            "cors_origins"
        }

        needs_restart = {
            "port", "host", "reload",
            "admin_username", "admin_password", "admin_secret_key"
        }

        updated_hot = [k for k in request_dict.keys() if k in hot_reloadable]
        updated_restart = [k for k in request_dict.keys() if k in needs_restart]

        # 生成詳細的反饋消息
        messages = []
        if updated_hot:
            messages.append(f"✅ 已即時生效: {', '.join(updated_hot)}")
        if updated_restart:
            messages.append(f"⚠️ 需重啟服務: {', '.join(updated_restart)}")

        detail_message = " | ".join(messages) if messages else "配置已更新"

        return EnvConfigResponse(
            success=True,
            config={
                "updated_keys": list(updates.keys()),
                "hot_reloaded": updated_hot,
                "needs_restart": updated_restart
            },
            message=detail_message,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置失敗: {str(e)}")


def _update_runtime_settings(updates: dict):
    """更新運行時配置（不需重啟即可生效的部分）"""
    # 更新 LLM 配置
    if "use_llm_extraction" in updates:
        settings.use_llm_extraction = updates["use_llm_extraction"]
    if "openai_api_key" in updates:
        settings.openai_api_key = updates["openai_api_key"]
    if "openai_api_base" in updates:
        settings.openai_api_base = updates["openai_api_base"]
    if "openai_model" in updates:
        settings.openai_model = updates["openai_model"]
    if "default_code_extraction_method" in updates:
        settings.default_code_extraction_method = updates["default_code_extraction_method"]

    # 更新 Cloudflare 配置
    if "use_cloudflare_kv" in updates:
        settings.use_cloudflare_kv = updates["use_cloudflare_kv"]
    if "cf_account_id" in updates:
        settings.cf_account_id = updates["cf_account_id"]
    if "cf_kv_namespace_id" in updates:
        settings.cf_kv_namespace_id = updates["cf_kv_namespace_id"]
    if "cf_api_token" in updates:
        settings.cf_api_token = updates["cf_api_token"]

    # 更新域名配置 (新增)
    if "custom_domains" in updates:
        settings.custom_domains = updates["custom_domains"]
    if "default_domains" in updates:
        settings.default_domains = updates["default_domains"]
    if "enable_custom_domains" in updates:
        settings.enable_custom_domains = updates["enable_custom_domains"]
    if "enable_builtin_domains" in updates:
        settings.enable_builtin_domains = updates["enable_builtin_domains"]

    # 更新郵件配置 (新增)
    if "email_ttl" in updates:
        settings.email_ttl = updates["email_ttl"]
    if "mail_check_interval" in updates:
        settings.mail_check_interval = updates["mail_check_interval"]
    if "max_mails_per_email" in updates:
        settings.max_mails_per_email = updates["max_mails_per_email"]

    # 更新 CORS 配置 (新增)
    if "cors_origins" in updates:
        # 解析 CORS origins（支持字符串或列表）
        if isinstance(updates["cors_origins"], str):
            try:
                import json
                settings.cors_origins = json.loads(updates["cors_origins"])
            except json.JSONDecodeError:
                # 如果不是 JSON 格式，按逗號分割
                settings.cors_origins = [x.strip() for x in updates["cors_origins"].split(",")]
        else:
            settings.cors_origins = updates["cors_origins"]

    # 重新初始化 LLM 服務
    try:
        from app.services.llm_code_service import llm_code_service

        llm_code_service.api_key = settings.openai_api_key
        llm_code_service.api_base = settings.openai_api_base
        llm_code_service.model = settings.openai_model
        llm_code_service.use_llm = settings.use_llm_extraction and bool(
            settings.openai_api_key
        )
    except ImportError:
        pass  # LLM 服務可能不存在

    # 重新初始化 Cloudflare KV 服務 (新增)
    try:
        from app.services.kv_mail_service import kv_client

        if settings.use_cloudflare_kv:
            kv_client.account_id = settings.cf_account_id
            kv_client.namespace_id = settings.cf_kv_namespace_id
            kv_client.api_token = settings.cf_api_token
    except ImportError:
        pass  # KV 服務可能不存在

    # 重新計算活躍域名列表 (enhanced)
    try:
        import app.config as config_module

        # 保存舊的域名列表以便比較
        old_domains = config_module.EMAIL_DOMAINS.copy() if hasattr(config_module, 'EMAIL_DOMAINS') else []

        # 強制刷新域名列表(考慮 Cloudflare KV 域名)
        config_module.EMAIL_DOMAINS = config_module.get_active_domains()

        # Log domain changes for debugging
        new_domains = config_module.EMAIL_DOMAINS
        added = set(new_domains) - set(old_domains)
        removed = set(old_domains) - set(new_domains)

        if added or removed:
            print(f"✅ Domain list updated:")
            print(f"   Total domains: {len(new_domains)}")
            if added:
                print(f"   Added: {added}")
            if removed:
                print(f"   Removed: {removed}")
        else:
            print(f"ℹ️  Domain list unchanged ({len(new_domains)} domains)")
    except Exception as e:
        print(f"⚠️ Warning: Failed to refresh domain list: {e}")


# ==================== 日誌管理 API ====================


@router.get("/logs/stream")
async def stream_logs(current_user: str = Depends(get_current_user)):
    """
    SSE 實時日誌流
    需要登入
    """

    async def event_generator():
        """生成 SSE 事件"""
        queue = await log_service.subscribe()
        try:
            # 發送連接成功消息
            yield f"data: {{'type':'connected','message':'日誌流已連接'}}\n\n"

            # 持續發送日誌
            while True:
                try:
                    # 等待新日誌（超時 30 秒發送心跳）
                    entry = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {entry.to_json()}\n\n"
                except asyncio.TimeoutError:
                    # 發送心跳保持連接
                    yield f": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            # 取消訂閱
            await log_service.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 緩衝
        },
    )


@router.get("/logs/history")
async def get_log_history(
    current_user: str = Depends(get_current_user),
    levels: Optional[str] = Query(None, description="逗號分隔的日誌級別 (debug,info,warning,error,success)"),
    types: Optional[str] = Query(None, description="逗號分隔的日誌類型 (request,response,email_gen,...)"),
    keyword: Optional[str] = Query(None, description="關鍵字搜索"),
    limit: int = Query(100, ge=1, le=1000, description="最大返回數量")
):
    """
    獲取歷史日誌（帶過濾）
    需要登入
    """

    # 解析過濾參數
    level_filters = None
    if levels:
        try:
            level_filters = [LogLevel(l.strip()) for l in levels.split(",") if l.strip()]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"無效的日誌級別: {e}")

    type_filters = None
    if types:
        try:
            type_filters = [LogType(t.strip()) for t in types.split(",") if t.strip()]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"無效的日誌類型: {e}")

    # 獲取過濾後的歷史記錄
    logs = log_service.get_history(
        levels=level_filters,
        types=type_filters,
        keyword=keyword,
        limit=limit
    )

    return {
        "success": True,
        "count": len(logs),
        "logs": logs
    }


@router.get("/logs/stats")
async def get_log_stats(current_user: str = Depends(get_current_user)):
    """
    獲取日誌統計信息
    需要登入
    """
    import traceback

    try:
        stats = await log_service.get_stats()

        # 檢查統計中是否包含錯誤信息
        if "error" in stats:
            # 記錄錯誤到日誌服務
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.SYSTEM,
                message=f"統計服務內部錯誤: {stats['error']}",
                details={
                    "error_type": "stats_internal_error",
                    "error_message": stats['error'],
                    "error_detail": stats.get('error_detail', ''),
                }
            )

            # 返回帶有錯誤信息的響應（但不拋出異常，保持 200 狀態碼）
            return {
                "success": False,
                "stats": stats,
                "error": stats['error'],
                "message": f"统计服务部分功能异常: {stats['error']}"
            }

        # 正常情況
        return {
            "success": True,
            "stats": stats
        }

    except Exception as e:
        # 捕獲所有未預期的異常
        error_detail = traceback.format_exc()
        error_message = f"獲取日誌統計失敗: {str(e)}"

        # 記錄詳細錯誤到日誌服務（如果日誌服務可用）
        try:
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.ERROR,
                message=error_message,
                details={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "error_traceback": error_detail,
                    "endpoint": "/admin/logs/stats",
                    "user": current_user
                }
            )
        except:
            # 如果日誌服務也失敗了，至少輸出到控制台
            print(f"❌ 無法記錄錯誤日誌: {error_message}")
            print(f"完整錯誤堆棧:\n{error_detail}")

        # 返回詳細錯誤響應（5xx 狀態碼）
        raise HTTPException(
            status_code=500,
            detail={
                "error": error_message,
                "error_type": type(e).__name__,
                "error_detail": error_detail if settings.reload else str(e),  # 開發模式顯示完整堆棧
                "timestamp": datetime.now().isoformat()
            }
        )


@router.post("/logs/clear")
async def clear_logs(current_user: str = Depends(get_current_user)):
    """
    清空日誌歷史
    需要登入
    """

    log_service.clear_history()
    return {
        "success": True,
        "message": "日誌已清空"
    }


@router.get("/logs/ip-stats")
async def get_ip_statistics(current_user: str = Depends(get_current_user)):
    """
    獲取 IP 統計信息（唯一 IP + 地理位置）
    需要登入

    使用免費的 ip-api.com 進行地理位置查詢
    支持批量查詢（最多 100 個 IP）
    """
    import httpx
    from collections import defaultdict

    # 提取唯一 IP
    ip_requests = defaultdict(int)  # IP -> 請求次數

    for entry in log_service.history:
        if entry.details and 'client_ip' in entry.details:
            ip = entry.details['client_ip']
            if ip and ip != 'unknown':
                ip_requests[ip] += 1

    if not ip_requests:
        return {
            "success": True,
            "total_ips": 0,
            "ips": [],
            "message": "暫無 IP 數據"
        }

    # 批量查詢地理位置（使用 ip-api.com）
    ip_list = list(ip_requests.keys())
    geo_data = []

    try:
        # ip-api.com 支持批量查詢（POST 請求，最多 100 個 IP）
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 分批處理（每批 100 個）
            for i in range(0, len(ip_list), 100):
                batch = ip_list[i:i+100]

                try:
                    # 批量查詢
                    response = await client.post(
                        "http://ip-api.com/batch",
                        json=batch,
                        params={"fields": "status,message,country,countryCode,region,regionName,city,lat,lon,isp,query"}
                    )

                    if response.status_code == 200:
                        batch_results = response.json()

                        for result in batch_results:
                            ip = result.get('query', '')
                            if result.get('status') == 'success':
                                geo_data.append({
                                    "ip": ip,
                                    "country": result.get('country', '-'),
                                    "country_code": result.get('countryCode', '-'),
                                    "region": result.get('regionName', '-'),
                                    "city": result.get('city', '-'),
                                    "isp": result.get('isp', '-'),
                                    "lat": result.get('lat'),
                                    "lon": result.get('lon'),
                                    "requests": ip_requests.get(ip, 0),
                                    "status": "success"
                                })
                            else:
                                # 查詢失敗（例如私有 IP）
                                geo_data.append({
                                    "ip": ip,
                                    "country": "未知",
                                    "country_code": "-",
                                    "region": "-",
                                    "city": "-",
                                    "isp": "-",
                                    "lat": None,
                                    "lon": None,
                                    "requests": ip_requests.get(ip, 0),
                                    "status": "fail",
                                    "message": result.get('message', '查詢失敗')
                                })
                    else:
                        # API 請求失敗，使用備用數據
                        for ip in batch:
                            geo_data.append({
                                "ip": ip,
                                "country": "查詢失敗",
                                "country_code": "-",
                                "region": "-",
                                "city": "-",
                                "isp": "-",
                                "lat": None,
                                "lon": None,
                                "requests": ip_requests.get(ip, 0),
                                "status": "error"
                            })

                except Exception as e:
                    # 單批查詢失敗，使用備用數據
                    for ip in batch:
                        geo_data.append({
                            "ip": ip,
                            "country": "查询异常",
                            "country_code": "-",
                            "region": "-",
                            "city": "-",
                            "isp": "-",
                            "lat": None,
                            "lon": None,
                            "requests": ip_requests.get(ip, 0),
                            "status": "error",
                            "error": str(e)
                        })

    except Exception as e:
        # 全局錯誤，返回 IP 列表但不包含地理位置
        geo_data = [
            {
                "ip": ip,
                "country": "查詢服務不可用",
                "country_code": "-",
                "region": "-",
                "city": "-",
                "isp": "-",
                "lat": None,
                "lon": None,
                "requests": count,
                "status": "error"
            }
            for ip, count in ip_requests.items()
        ]

    # 按請求次數排序
    geo_data.sort(key=lambda x: x['requests'], reverse=True)

    # 統計國家分佈
    country_stats = defaultdict(int)
    for item in geo_data:
        if item.get('status') == 'success':
            country_stats[item['country']] += item['requests']

    return {
        "success": True,
        "total_ips": len(geo_data),
        "total_requests": sum(ip_requests.values()),
        "ips": geo_data,
        "country_stats": dict(sorted(country_stats.items(), key=lambda x: x[1], reverse=True)),
        "message": f"成功統計 {len(geo_data)} 個唯一 IP"
    }


@router.get("/logs/files")
async def list_log_files(current_user: str = Depends(get_current_user)):
    """
    列出所有日誌文件
    需要登入
    """

    if not log_service.log_dir or not log_service.log_dir.exists():
        return {
            "success": True,
            "files": [],
            "message": "文件日誌未啟用"
        }

    try:
        files = []
        for file_path in sorted(log_service.log_dir.glob("*.log*"), reverse=True):
            stat = file_path.stat()
            files.append({
                "name": file_path.name,
                "size": stat.st_size,
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

        return {
            "success": True,
            "files": files,
            "log_dir": str(log_service.log_dir.absolute())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取日誌文件失敗: {str(e)}")


@router.get("/logs/download/{filename}")
async def download_log_file(
    filename: str,
    current_user: str = Depends(get_current_user)
):
    """
    下載指定日誌文件
    需要登入
    """

    if not log_service.log_dir:
        raise HTTPException(status_code=404, detail="文件日誌未啟用")

    # 安全檢查：防止目錄遍歷攻擊
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="無效的文件名")

    file_path = log_service.log_dir / filename
    
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    from fastapi.responses import FileResponse
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="text/plain"
    )


# ==================== Cloudflare 配置辅助 API ====================


# ==================== 輔助函數：配置來源檢測 ====================

from typing import Tuple

async def _get_config_value(
    request_value: Optional[str],
    env_key: str,
    settings_value: Optional[str]
) -> Tuple[Optional[str], str]:
    """
    獲取配置值並追蹤來源

    優先級：
    1. 請求參數（前端輸入框）
    2. .env 文件
    3. 環境變數（settings）

    Args:
        request_value: 請求參數值（前端輸入框）
        env_key: 環境變數鍵名（大寫）
        settings_value: settings 中的值（已從環境變數載入）

    Returns:
        (配置值, 來源標記)
        來源標記: "input_box" | "env_file" | "environment_variable" | "not_found"
    """
    # 1. 優先使用請求參數（前端輸入框）
    if request_value and request_value.strip():
        return (request_value, "input_box")

    # 2. 檢查 .env 文件
    try:
        env_data = env_service.read_env()
        if env_key in env_data and env_data[env_key] and env_data[env_key].strip():
            return (env_data[env_key], "env_file")
    except Exception:
        pass  # .env 讀取失敗，繼續嘗試其他來源

    # 3. 使用 settings（環境變數）
    if settings_value and settings_value.strip():
        return (settings_value, "environment_variable")

    # 4. 未找到
    return (None, "not_found")


class CloudflareTestRequest(BaseModel):
    """Cloudflare 连接测试请求（所有字段可選）"""
    cf_account_id: Optional[str] = None
    cf_kv_namespace_id: Optional[str] = None
    cf_api_token: Optional[str] = None


class EnsureNamespaceRequest(BaseModel):
    """确保 KV Namespace 存在请求"""
    title: str = "EMAIL_STORAGE"
    cf_account_id: Optional[str] = None
    cf_api_token: Optional[str] = None


class WranglerSnippetResponse(BaseModel):
    success: bool
    binding: str
    namespace_id: str
    preview_id: Optional[str] = None
    snippet: str
    message: Optional[str] = None


class WriteWranglerRequest(BaseModel):
    file_path: str
    binding: str = "EMAIL_STORAGE"
    namespace_id: str
    preview_id: Optional[str] = None
    confirm: bool = True


@router.get("/cloudflare/wizard")
async def get_cloudflare_wizard(current_user: str = Depends(get_current_user)):
    """
    获取 Cloudflare 配置向导步骤
    需要登录
    """
    try:
        steps = cloudflare_helper.get_wizard_steps()
        return {
            "success": True,
            "steps": steps,
            "message": "配置向导加载成功"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载向导失败: {str(e)}")


@router.post("/cloudflare/test-connection")
async def test_cloudflare_connection(
    request: CloudflareTestRequest,
    current_user: str = Depends(get_current_user)
):
    """
    测试 Cloudflare KV 连接
    需要登录

    执行三层验证:
    1. API Token 权限检查
    2. Account ID 验证
    3. Namespace ID 访问测试
    """
    try:
        result = await cloudflare_helper.test_connection(
            account_id=request.cf_account_id,
            namespace_id=request.cf_kv_namespace_id,
            api_token=request.cf_api_token
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"测试连接失败: {str(e)}")


@router.post("/cloudflare/auto-detect")
async def auto_detect_cloudflare(current_user: str = Depends(get_current_user)):
    """
    自动检测 Wrangler CLI 配置
    需要登录

    尝试从本地 Wrangler CLI 读取:
    - Account ID (wrangler whoami)
    - KV Namespace ID (wrangler kv:namespace list)
    """
    try:
        result = await cloudflare_helper.auto_detect_wrangler()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"自动检测失败: {str(e)}")


@router.get("/cloudflare/kv/namespaces")
async def list_kv_namespaces(
    search: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user)
):
    """列出 KV Namespaces（需要登录）"""
    account_id = settings.cf_account_id
    api_token = settings.cf_api_token
    if not account_id or not api_token:
        raise HTTPException(status_code=400, detail="请先填写 CF_ACCOUNT_ID 与 CF_API_TOKEN 并保存")

    result = await cloudflare_helper.list_kv_namespaces(account_id, api_token, search)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=f"列出命名空间失败: {result.get('message')}")
    return {"success": True, "namespaces": result.get("namespaces", [])}


@router.post("/cloudflare/kv/ensure-namespace")
async def ensure_kv_namespace(
    request: EnsureNamespaceRequest,
    current_user: str = Depends(get_current_user)
):
    """确保 namespace 存在；不存在则创建（需要登录）"""
    account_id = request.cf_account_id or settings.cf_account_id
    api_token = request.cf_api_token or settings.cf_api_token
    if not account_id or not api_token:
        raise HTTPException(status_code=400, detail="缺少 CF_ACCOUNT_ID 或 CF_API_TOKEN")

    result = await cloudflare_helper.ensure_kv_namespace(account_id, api_token, request.title)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=f"操作失败: {result.get('message')}")

    # 若创建或找到，回传 id
    return {"success": True, "created": result.get("created", False), "id": result.get("id"), "title": request.title}


@router.get("/cloudflare/wrangler-snippet", response_model=WranglerSnippetResponse)
async def get_wrangler_snippet(
    binding: str = Query("EMAIL_STORAGE"),
    namespace_id: Optional[str] = Query(None),
    preview_id: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user)
):
    """生成 wrangler.toml 片段（基于当前配置或查询参数）"""
    ns_id = namespace_id or settings.cf_kv_namespace_id
    if not ns_id:
        raise HTTPException(status_code=400, detail="缺少 Namespace ID，请先填写/创建")

    snippet = cloudflare_helper.build_wrangler_snippet(binding, ns_id, preview_id)
    return WranglerSnippetResponse(success=True, binding=binding, namespace_id=ns_id, preview_id=preview_id, snippet=snippet, message="复制到 workers/wrangler.toml")


@router.post("/cloudflare/write-wrangler")
async def write_wrangler_file(
    req: WriteWranglerRequest,
    current_user: str = Depends(get_current_user)
):
    """写入/更新 wrangler.toml（可选，需显式确认）"""
    if not req.confirm:
        raise HTTPException(status_code=400, detail="需要 confirm=true 才能写入文件")

    abs_path = os.path.abspath(req.file_path)
    project_root = os.path.abspath(os.getcwd())
    if not abs_path.startswith(project_root):
        raise HTTPException(status_code=400, detail="出于安全考虑，只允许写入项目目录内的文件")

    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail=f"文件不存在: {abs_path}")

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 查找匹配 binding 的 [[kv_namespaces]] 块
        pattern = re.compile(r"\[\[kv_namespaces\]\][^\[]*?binding\s*=\s*\"" + re.escape(req.binding) + r"\"[\s\S]*?(?=(\[\[kv_namespaces\]\]|$))", re.MULTILINE)
        match = pattern.search(content)
        block_snippet = cloudflare_helper.build_wrangler_snippet(req.binding, req.namespace_id, req.preview_id)

        if match:
            # 在现有块内替换 id 行（或追加）
            block = match.group(0)
            # 替换 id= 行
            if re.search(r"^\s*id\s*=\s*\".*?\"\s*$", block, re.MULTILINE):
                block_new = re.sub(r"^\s*id\s*=\s*\".*?\"\s*$", f"id = \"{req.namespace_id}\"", block, flags=re.MULTILINE)
            else:
                block_new = block.rstrip() + f"\nid = \"{req.namespace_id}\"\n"

            # preview_id（可选）
            if req.preview_id:
                if re.search(r"^\s*preview_id\s*=\s*\".*?\"\s*$", block_new, re.MULTILINE):
                    block_new = re.sub(r"^\s*preview_id\s*=\s*\".*?\"\s*$", f"preview_id = \"{req.preview_id}\"", block_new, flags=re.MULTILINE)
                else:
                    block_new = block_new.rstrip() + f"\npreview_id = \"{req.preview_id}\"\n"

            content_new = content[:match.start()] + block_new + content[match.end():]
        else:
            # 追加新块
            sep = "\n\n" if not content.endswith("\n") else "\n"
            content_new = content + sep + block_snippet

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content_new)

        return {"success": True, "file": abs_path, "message": "wrangler.toml 已更新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入失败: {str(e)}")


@router.get("/cloudflare/deploy-status")
async def check_deploy_status(current_user: str = Depends(get_current_user)):
    """
    检查 Cloudflare KV 配置状态（Docker 友好）
    基于配置完整性检查，而非文件存在性
    需要登录
    """
    import os

    try:
        # 方法 1：檢查配置完整性（主要方法，Docker 友好）
        has_complete_config = all([
            settings.cf_account_id and settings.cf_account_id.strip(),
            settings.cf_kv_namespace_id and settings.cf_kv_namespace_id.strip(),
            settings.cf_api_token and settings.cf_api_token.strip()
        ])

        if has_complete_config:
            # 配置完整，視為已部署
            return {
                "success": True,
                "deployed": True,
                "method": "config",
                "account_id": settings.cf_account_id[:8] + "..." if len(settings.cf_account_id) > 8 else settings.cf_account_id,
                "namespace_id": settings.cf_kv_namespace_id[:8] + "..." if len(settings.cf_kv_namespace_id) > 8 else settings.cf_kv_namespace_id,
                "api_token_configured": bool(settings.cf_api_token and settings.cf_api_token.strip()),
                "message": "✅ Cloudflare KV 配置完整"
            }

        # 方法 2：檢查配置文件（本地部署專用，可選）
        config_file = os.path.join(os.path.dirname(__file__), "../..", ".cloudflare_config")

        if os.path.exists(config_file):
            # 讀取配置文件內容
            with open(config_file, 'r') as f:
                content = f.read()

            # 解析關鍵信息
            namespace_id = None
            worker_url = None
            deploy_time = None

            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('CF_KV_NAMESPACE_ID='):
                    namespace_id = line.split('=', 1)[1].strip()
                elif line.startswith('WORKER_URL='):
                    worker_url = line.split('=', 1)[1].strip()
                elif line.startswith('# 生成时间:'):
                    deploy_time = line.split(':', 1)[1].strip()

            return {
                "success": True,
                "deployed": True,
                "method": "file",
                "namespace_id": namespace_id,
                "worker_url": worker_url,
                "deploy_time": deploy_time,
                "message": "✅ 檢測到本地部署配置文件"
            }

        # 配置不完整
        missing_items = []
        if not settings.cf_account_id or not settings.cf_account_id.strip():
            missing_items.append("CF_ACCOUNT_ID")
        if not settings.cf_kv_namespace_id or not settings.cf_kv_namespace_id.strip():
            missing_items.append("CF_KV_NAMESPACE_ID")
        if not settings.cf_api_token or not settings.cf_api_token.strip():
            missing_items.append("CF_API_TOKEN")

        return {
            "success": True,
            "deployed": False,
            "missing_config": missing_items,
            "message": f"⚠️ 缺少配置: {', '.join(missing_items)}\n\n" +
                      "Docker 環境：請通過環境變數或 Admin 界面配置\n" +
                      "本地環境：請運行 cd workers && ./deploy.sh"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检查部署状态失败: {str(e)}")


@router.post("/cloudflare/test-and-check-stream")
async def test_and_check_stream(
    request: Optional[CloudflareTestRequest] = None,
    current_user: str = Depends(get_current_user)
):
    """
    流式检查：逐步执行并实时推送结果 (SSE)
    需要登录

    使用 Server-Sent Events (SSE) 实现流式响应，
    每个检查阶段完成后立即推送结果给前端。
    """
    import json

    async def event_generator():
        try:
            # ========== 步骤 0: 初始化 ==========
            data = {"stage": "init", "message": "🚀 开始检查...", "progress": 0}
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.1)

            # 收集配置值
            account_id, account_id_source = await _get_config_value(
                request.cf_account_id if request else None,
                "CF_ACCOUNT_ID",
                settings.cf_account_id
            )

            namespace_id, namespace_id_source = await _get_config_value(
                request.cf_kv_namespace_id if request else None,
                "CF_KV_NAMESPACE_ID",
                settings.cf_kv_namespace_id
            )

            api_token, api_token_source = await _get_config_value(
                request.cf_api_token if request else None,
                "CF_API_TOKEN",
                settings.cf_api_token
            )

            # 检查配置完整性
            missing_items = []
            if not account_id or not account_id.strip():
                missing_items.append("CF_ACCOUNT_ID")
            if not namespace_id or not namespace_id.strip():
                missing_items.append("CF_KV_NAMESPACE_ID")
            if not api_token or not api_token.strip():
                missing_items.append("CF_API_TOKEN")

            if missing_items:
                missing_str = ", ".join(missing_items)
                data = {
                    "stage": "error",
                    "message": f"❌ 配置不完整，缺少：{missing_str}",
                    "missing": missing_items,
                    "progress": 0
                }
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                return

            # ========== 步骤 1: 验证 API Token ==========
            data = {"stage": "token", "message": "🔑 验证 API Token...", "progress": 20}
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            token_check = await cloudflare_helper._verify_token(api_token)

            data = {
                "stage": "token",
                "status": token_check["status"],
                "message": f"{token_check['icon']} {token_check['message']}",
                "progress": 30,
                "result": token_check
            }
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            if token_check["status"] != "passed":
                # 改为警告而非错误，继续执行后续检查
                data = {
                    "stage": "warning",
                    "message": f"⚠️ Token 验证未通过，但服务可能仍然可用\n💡 提示：{token_check['message']}\n建议：先尝试使用服务，如遇实际问题再调整配置",
                    "progress": 30,
                    "can_continue": True,
                    "result": token_check
                }
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                # 不返回，继续后续检查

            # ========== 步骤 2: 验证 Account ID ==========
            data = {"stage": "account", "message": "🆔 验证 Account ID...", "progress": 40}
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            account_check = await cloudflare_helper._verify_account(account_id, api_token)

            data = {
                "stage": "account",
                "status": account_check["status"],
                "message": f"{account_check['icon']} {account_check['message']}",
                "progress": 50,
                "result": account_check
            }
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            if account_check["status"] != "passed":
                # 改为警告而非错误，继续执行后续检查
                data = {
                    "stage": "warning",
                    "message": f"⚠️ Account 验证未通过，但服务可能仍然可用\n💡 提示：{account_check['message']}\n建议：先尝试使用服务，如遇实际问题再调整配置",
                    "progress": 50,
                    "can_continue": True,
                    "result": account_check
                }
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                # 不返回，继续后续检查

            # ========== 步骤 3: 验证 Namespace ID ==========
            data = {"stage": "namespace", "message": "📦 验证 KV Namespace...", "progress": 60}
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            namespace_check = await cloudflare_helper._verify_namespace(account_id, namespace_id, api_token)

            data = {
                "stage": "namespace",
                "status": namespace_check["status"],
                "message": f"{namespace_check['icon']} {namespace_check['message']}",
                "progress": 70,
                "result": namespace_check
            }
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            if namespace_check["status"] != "passed":
                # 改为警告而非错误，继续执行后续检查
                data = {
                    "stage": "warning",
                    "message": f"⚠️ Namespace 验证未通过，但服务可能仍然可用\n💡 提示：{namespace_check['message']}\n建议：先尝试使用服务，如遇实际问题再调整配置",
                    "progress": 70,
                    "can_continue": True,
                    "result": namespace_check
                }
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                # 不返回，继续后续检查

            # ========== 步骤 4: 配置匹配度检查 ==========
            data = {"stage": "match", "message": "🔗 检查配置匹配度...", "progress": 75}
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            match_result = await cloudflare_helper.verify_config_match(account_id, namespace_id, api_token)

            match_status = "passed" if match_result["match"] else "warning"
            match_message = "✅ 配置匹配" if match_result["match"] else "⚠️ 配置不匹配"
            data = {
                "stage": "match",
                "status": match_status,
                "message": match_message,
                "progress": 80,
                "result": match_result
            }
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            # ========== 步骤 5: 域名检查（带进度） ==========
            data = {"stage": "domains", "message": "📧 检查域名配置...", "progress": 85}
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            # 获取域名列表
            zones_result = await cloudflare_helper.list_account_zones(account_id, api_token)
            zones = zones_result.get("zones", [])

            if zones:
                num_zones = len(zones)
                data = {
                    "stage": "domains",
                    "message": f"📋 发现 {num_zones} 个域名，开始检查...",
                    "progress": 87
                }
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

                # 检查所有域名的 Email Routing 状态
                email_routing_status = {}

                for i, zone in enumerate(zones[:10]):  # 限制只检查前10个域名
                    zone_name = zone.get("name")
                    zone_id = zone.get("id")

                    # 检查单个域名
                    routing_status = await cloudflare_helper.check_email_routing_status(zone_id, api_token)
                    email_routing_status[zone_name] = routing_status

                    # 推送进度
                    check_count = min(len(zones), 10)
                    current_progress = 87 + int((i + 1) / check_count * 8)  # 87-95
                    data = {
                        "stage": "domains",
                        "message": f"📧 检查域名 {i+1}/{check_count}: {zone_name}",
                        "progress": current_progress,
                        "current_domain": zone_name,
                        "domain_status": routing_status
                    }
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

                # 域名检查完成
                check_count = min(len(zones), 10)
                data = {
                    "stage": "domains",
                    "status": "passed",
                    "message": f"✅ 域名检查完成 ({check_count} 个)",
                    "progress": 95,
                    "result": {"email_routing_status": email_routing_status, "total_zones": len(zones)}
                }
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            else:
                data = {
                    "stage": "domains",
                    "status": "warning",
                    "message": "⚠️ 未检测到域名或无权限访问",
                    "progress": 95
                }
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            # ========== 完成 ==========
            data = {"stage": "done", "message": "🎉 所有检查完成！", "progress": 100, "success": True}
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        except Exception as e:
            error_msg = str(e)
            data = {
                "stage": "error",
                "message": f"⚠️ 检查过程中遇到错误: {error_msg}\n\n💡 但这不意味着服务无法工作！\n建议：先尝试使用服务，如遇实际问题再返回此处调整配置。",
                "error": error_msg,
                "can_continue": True
            }
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/cloudflare/test-and-check")
async def test_and_check_cloudflare(
    request: Optional[CloudflareTestRequest] = None,  # ⭐ 接受請求體
    current_user: str = Depends(get_current_user)
):
    """
    統一檢查：配置完整性 + 連接測試
    需要登錄

    ⭐ 新功能：
    - 優先使用前端輸入框的值進行測試
    - 追蹤配置來源（輸入框 vs .env vs 環境變數）
    - 檢測 Docker 環境

    執行步驟：
    1. 收集配置值（優先級：請求參數 > .env > 環境變數）
    2. 檢查配置是否存在
    3. 如果配置存在，執行完整的連接測試（Token → Account → Namespace）
    4. 返回詳細的分步驟結果、配置來源和修復建議

    Returns:
        {
            "success": bool,
            "config_check": {...},  # 配置檢查結果
            "connection_test": {...},  # 連接測試結果（如果配置完整）
            "config_source": {...},  # 配置來源
            "is_docker": bool,  # 是否在 Docker 環境中運行
            "env_file_exists": bool,  # .env 文件是否存在
            "message": str,
            "suggestions": []  # 修復建議
        }
    """
    try:
        result = {
            "success": False,
            "config_check": {},
            "connection_test": None,
            "config_source": {},
            "is_docker": False,
            "env_file_exists": False,
            "env_file_path": None,
            "message": "",
            "suggestions": []
        }

        # ========== 步驟 1: 配置來源檢測和值收集 ==========
        # 使用輔助函數獲取每個配置項的值和來源
        account_id, account_id_source = await _get_config_value(
            request.cf_account_id if request else None,
            "CF_ACCOUNT_ID",
            settings.cf_account_id
        )

        namespace_id, namespace_id_source = await _get_config_value(
            request.cf_kv_namespace_id if request else None,
            "CF_KV_NAMESPACE_ID",
            settings.cf_kv_namespace_id
        )

        api_token, api_token_source = await _get_config_value(
            request.cf_api_token if request else None,
            "CF_API_TOKEN",
            settings.cf_api_token
        )

        # 記錄配置來源
        result["config_source"] = {
            "cf_account_id": account_id_source,
            "cf_kv_namespace_id": namespace_id_source,
            "cf_api_token": api_token_source
        }

        # ========== 步驟 2: Docker 環境檢測 ==========
        result["is_docker"] = (
            os.path.exists("/.dockerenv") or
            os.environ.get("DOCKER_CONTAINER") == "true"
        )

        env_file_path = os.path.join(os.getcwd(), ".env")
        result["env_file_exists"] = os.path.exists(env_file_path)
        if result["env_file_exists"]:
            result["env_file_path"] = env_file_path

        # ========== 步驟 3: 配置完整性檢查 ==========
        missing_items = []
        if not account_id or not account_id.strip():
            missing_items.append("CF_ACCOUNT_ID")
        if not namespace_id or not namespace_id.strip():
            missing_items.append("CF_KV_NAMESPACE_ID")
        if not api_token or not api_token.strip():
            missing_items.append("CF_API_TOKEN")

        result["config_check"] = {
            "complete": len(missing_items) == 0,
            "missing_items": missing_items,
            "cf_account_id_configured": bool(account_id and account_id.strip()),
            "cf_kv_namespace_id_configured": bool(namespace_id and namespace_id.strip()),
            "cf_api_token_configured": bool(api_token and api_token.strip())
        }

        # 配置不完整 - 返回提示
        if missing_items:
            result["message"] = f"⚠️ 配置不完整，缺少：{', '.join(missing_items)}"
            result["suggestions"] = [
                "1️⃣ 方法一：使用「自動檢測」按鈕（如果已安裝 Wrangler CLI）",
                "2️⃣ 方法二：使用「配置向導」按鈕，按步驟手動配置",
                "3️⃣ 方法三：直接在下方表單填寫配置並保存"
            ]

            # 針對性建議
            if "CF_ACCOUNT_ID" in missing_items:
                result["suggestions"].append("📝 獲取 Account ID: https://dash.cloudflare.com/ → 右側「⋮」→ 複製帳戶 ID")
            if "CF_KV_NAMESPACE_ID" in missing_items:
                result["suggestions"].append("📦 創建 Namespace: wrangler kv namespace create EMAIL_STORAGE")
            if "CF_API_TOKEN" in missing_items:
                result["suggestions"].append("🔑 創建 API Token: https://dash.cloudflare.com/profile/api-tokens → 權限需要：Account Settings: Read + Workers KV Storage: Read")

            return result

        # ========== 步驟 4: 連接測試 ==========
        await log_service.log(
            level=LogLevel.INFO,
            log_type=LogType.SYSTEM,
            message="开始执行 Cloudflare KV 连接测试",
            details={
                "account_id": account_id[:8] + "..." if account_id else "None",
                "namespace_id": namespace_id[:8] + "..." if namespace_id else "None",
                "account_id_source": account_id_source,
                "namespace_id_source": namespace_id_source,
                "api_token_source": api_token_source
            }
        )

        connection_result = await cloudflare_helper.test_connection(
            account_id=account_id,
            namespace_id=namespace_id,
            api_token=api_token
        )

        result["connection_test"] = connection_result

        # 连接测试成功 - 继续进行配置匹配度检查
        if connection_result.get("success"):
            # ⭐ 步驟 5: 配置匹配度检查
            match_result = await cloudflare_helper.verify_config_match(
                account_id=account_id,
                namespace_id=namespace_id,
                api_token=api_token
            )

            result["config_match"] = match_result
            result["success"] = match_result.get("match", False)

            # ⭐ 步驟 6: 域名配置检查（新增 - 使用 Cloudflare API）
            cf_kv_domains_value = settings.cf_kv_domains

            # 使用 API 检查域名（如果连接成功）
            domains_check_api = await cloudflare_helper.check_domains_with_api(
                account_id=account_id,
                api_token=api_token,
                cf_kv_domains=cf_kv_domains_value
            )
            result["domains_check"] = domains_check_api

            if match_result.get("match"):
                # 完全匹配
                result["message"] = "✅ 配置完整且连接正常！所有配置项相互匹配"
                result["suggestions"] = match_result.get("suggestions", [])

                # 添加域名配置建议（使用新的 API 结果）
                if domains_check_api.get("success"):
                    result["suggestions"].append(
                        f"\n📧 域名配置: {domains_check_api.get('message', '')}"
                    )
                    # 添加 API 检查的详细建议
                    result["suggestions"].extend(domains_check_api.get("suggestions", []))
                else:
                    result["suggestions"].append(
                        f"\n⚠️ 域名检查: {domains_check_api.get('message', '')}"
                    )
                    result["suggestions"].extend(domains_check_api.get("suggestions", []))
            else:
                # 配置不匹配
                result["message"] = "⚠️ 连接正常，但配置项不匹配"
                result["suggestions"] = match_result.get("suggestions", [])

                # 域名配置建议
                if domains_check_api.get("success"):
                    result["suggestions"].append(
                        f"\n📧 域名配置: {domains_check_api.get('message', '')}"
                    )
                else:
                    result["suggestions"].append(
                        f"\n⚠️ 域名检查失败: {domains_check_api.get('message', '')}"
                    )

            await log_service.log(
                level=LogLevel.SUCCESS if result["success"] else LogLevel.WARNING,
                log_type=LogType.SYSTEM,
                message="Cloudflare KV 连接测试完成" + (" (配置匹配)" if result["success"] else " (配置不匹配)"),
                details={
                    "checks_passed": len(connection_result.get("checks", [])),
                    "overall_status": connection_result.get("overall_status"),
                    "config_match": match_result.get("match", False),
                    "issues": match_result.get("issues", []),
                    "domains_configured": domains_check_api.get("configured", False),
                    "domains_count": domains_check_api.get("count", 0)
                }
            )

            return result

        # 连接测试失败 - 分析失败原因并提供建议
        result["message"] = f"❌ {connection_result.get('message', '连接测试失败')}"

        # 根據失敗的檢查項提供針對性建議
        checks = connection_result.get("checks", [])
        for check in checks:
            check_name = check.get("name", "")
            check_status = check.get("status", "")
            check_message = check.get("message", "")

            if check_status == "failed":
                if "API Token" in check_name:
                    result["suggestions"].extend([
                        "🔑 API Token 问题：",
                        "  • 请前往 https://dash.cloudflare.com/profile/api-tokens 重新创建 Token",
                        "  • 确保 Token 拥有以下权限：",
                        "    - Account Settings: Read",
                        "    - Workers KV Storage: Read",
                        "  • 检查 Token 是否已过期"
                    ])
                elif "Account ID" in check_name:
                    result["suggestions"].extend([
                        "🆔 Account ID 问题：",
                        "  • 请前往 https://dash.cloudflare.com/",
                        "  • 点击右侧「⋮」按钮",
                        "  • 确认帐户 ID 是否正确（32 位十六进制字符串）",
                        f"  • 当前配置：{account_id[:8]}..." if account_id else "  • 当前配置：未设置"
                    ])
                elif "Namespace" in check_name:
                    result["suggestions"].extend([
                        "📦 KV Namespace 问题：",
                        "  • Namespace ID 不存在或无法访问",
                        "  • 请执行：wrangler kv namespace create EMAIL_STORAGE",
                        "  • 或前往 https://dash.cloudflare.com → Workers & Pages → KV",
                        "  • 检查 Namespace 是否已创建",
                        f"  • 当前配置：{namespace_id[:8]}..." if namespace_id else "  • 当前配置：未设置"
                    ])

        # 如果没有具体建议，提供通用建议
        if not result["suggestions"]:
            result["suggestions"] = [
                "⚠️ 连接测试失败，请检查以下项目：",
                "1. API Token 是否有效且未过期",
                "2. Account ID 是否正确",
                "3. KV Namespace 是否已创建",
                "4. 网络连接是否正常",
                "5. Cloudflare 服务是否正常运行"
            ]

        await log_service.log(
            level=LogLevel.ERROR,
            log_type=LogType.SYSTEM,
            message="Cloudflare KV 连接测试失败",
            details={
                "overall_status": connection_result.get("overall_status"),
                "failed_checks": [c for c in checks if c.get("status") == "failed"]
            }
        )

        return result

    except Exception as e:
        await log_service.log(
            level=LogLevel.ERROR,
            log_type=LogType.SYSTEM,
            message=f"统一检查异常: {str(e)}",
            details={
                "error_type": type(e).__name__,
                "error_message": str(e)
            }
        )

        raise HTTPException(
            status_code=500,
            detail=f"检查过程中发生错误: {str(e)}"
        )
