import time
import os
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Request
from app.config import get_active_domains
from app.models import HealthResponse
from app.services.storage_service import storage_service
from app.services.email_service import email_service
from app.config import settings
from app.i18n import get_current_language, get_translations_for_frontend, create_language_switcher_links

router = APIRouter(prefix="/api", tags=["System"])

# 记录启动时间
_start_time = time.time()


@router.get("/config")
async def get_frontend_config():
    """
    获取前端配置

    返回前端需要的配置信息，如默认验证码提取方法
    
    Returns:
        - default_code_extraction_method: 默认验证码提取方法 ("llm" 或 "pattern")
        - use_cloudflare_kv: 是否启用 Cloudflare KV
    """
    return {
        "success": True,
        "data": {
            "default_code_extraction_method": settings.default_code_extraction_method,
            "use_cloudflare_kv": settings.use_cloudflare_kv,
        }
    }


@router.get("/domains")
async def get_domains():
    """
    获取可用域名列表

    Returns:
        - domains: 所有可用域名列表
        - total: 域名总数
        - info: 域名配置信息
    """
    domains = get_active_domains()
    info = email_service.get_domain_info()

    return {
        "success": True,
        "data": {
            "domains": domains,
            "total": len(domains),
            "info": info,
        },
    }


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    健康检查
    """
    from datetime import datetime

    stats = storage_service.get_stats()
    uptime = int(time.time() - _start_time)

    return {
        "success": True,
        "status": "healthy",
        "timestamp": datetime.now(),
        "uptime": uptime,
        "active_emails": stats["active_emails"],
    }


@router.get("/test")
async def test_cloudflare_kv():
    """
    测试 Cloudflare Workers KV 连接

    此端点用于验证 Cloudflare KV 配置是否正确。
    仅在启用 USE_CLOUDFLARE_KV=true 时有效。

    Returns:
        - status: 服务状态
        - cloudflare_kv: KV 连接状态和统计信息
        - config: 当前配置信息
    """
    from app.config import settings
    from datetime import datetime

    result = {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "cloudflare_kv": {
            "enabled": settings.use_cloudflare_kv
        },
        "config": {
            "custom_domains_enabled": settings.enable_custom_domains,
            "builtin_domains_enabled": settings.enable_builtin_domains,
        }
    }

    # 如果启用了 Cloudflare KV，测试连接
    if settings.use_cloudflare_kv:
        try:
            from app.services.kv_mail_service import kv_client

            # 测试连接
            connected = await kv_client.test_connection()
            result["cloudflare_kv"]["connected"] = connected

            if connected:
                # 获取统计信息
                stats = await kv_client.get_stats()
                result["cloudflare_kv"]["stats"] = stats
                result["status"] = "ok"
            else:
                result["status"] = "error"
                result["cloudflare_kv"]["error"] = "无法连接到 Cloudflare KV"

        except Exception as e:
            result["status"] = "error"
            result["cloudflare_kv"]["error"] = str(e)
            result["cloudflare_kv"]["connected"] = False
    else:
        result["cloudflare_kv"]["message"] = "Cloudflare KV 未启用。在 .env 中设置 USE_CLOUDFLARE_KV=true 以启用。"

    return result


@router.get("/_debug/headers")
async def debug_request_headers(request: Request):
    """
    調試端點：顯示所有請求頭和提取的 IP 地址

    用於診斷反向代理配置問題，幫助確認是否正確傳遞了客戶端 IP 頭信息。

    Returns:
        - headers: 所有請求頭
        - client_ip: request.client.host（Docker 內部 IP）
        - extracted_ip: 從代理頭提取的���實 IP
        - debug_info: IP 提取過程的詳細信息
    """
    from app.middleware.logging_middleware import get_client_ip

    # 提取所有頭信息
    headers = dict(request.headers)

    # 提取 IP 相關信息
    client_ip = request.client.host if request.client else "unknown"
    extracted_ip = get_client_ip(request)

    # 調試信息：顯示每個 IP 提取步驟
    debug_info = {
        "step_1_x_forwarded_for": request.headers.get("X-Forwarded-For"),
        "step_2_x_real_ip": request.headers.get("X-Real-IP"),
        "step_3_cf_connecting_ip": request.headers.get("CF-Connecting-IP"),
        "step_4_client_host": client_ip,
        "final_extracted_ip": extracted_ip,
    }

    return {
        "success": True,
        "data": {
            "headers": headers,
            "client_ip_raw": client_ip,
            "extracted_ip": extracted_ip,
            "debug_info": debug_info,
            "message": "如果 extracted_ip 仍是私有 IP（172.x.x.x），請檢查反向代理配置"
        }
    }


@router.get("/_debug/external-inbox")
async def debug_external_inbox(email: str = Query(..., description="郵箱地址")):
    """調試用：代理外部郵箱API，僅在 DEBUG_EMAIL_FETCH=true 時可用。

    返回原始JSON以便定位問題，不做任何存儲或處理。
    """
    if not getattr(settings, "debug_email_fetch", False):
        raise HTTPException(status_code=403, detail="Debug endpoint disabled")

    import httpx
    from urllib.parse import quote

    base = getattr(settings, "email_api_url", "https://mail.chatgpt.org.uk/api/get-emails").rstrip("?&")
    url = f"{base}{'&' if '?' in base else '?'}email={quote(email)}"
    ssl_verify = bool(getattr(settings, "email_api_ssl_verify", True))
    headers = {"User-Agent": "Mozilla/5.0"}

    async with httpx.AsyncClient(timeout=10.0, verify=ssl_verify) as client:
        try:
            resp = await client.get(url, headers=headers)
            status = resp.status_code
            try:
                body = resp.json()
            except Exception:
                body = {"text": (resp.text[:2000] if resp.text else "")}
            return {"success": True, "url": url, "status": status, "data": body}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/i18n/translations")
async def get_i18n_translations(request: Request):
    """
    获取前端翻译数据
    
    Returns:
        - language: 当前语言
        - translations: 翻译数据
        - availableLanguages: 可用语言列表
    """
    try:
        # 安全地获取当前语言
        current_language = getattr(request.state, 'language', 'en-US')
        translations = get_translations_for_frontend(current_language)
        
        return {
            "success": True,
            "data": translations
        }
    except Exception as e:
        # 返回错误信息而不是抛出异常
        return {
            "success": False,
            "error": f"Failed to load translations: {str(e)}",
            "data": {
                "language": "en-US",
                "translations": {},
                "availableLanguages": {"en-US": "English", "zh-CN": "简体中文"}
            }
        }


@router.get("/i18n/language-switcher")
async def get_language_switcher_links(request: Request):
    """
    获取语言切换链接
    
    Returns:
        - currentLanguage: 当前语言
        - switchUrls: 各语言的切换链接
    """
    try:
        # 安全地获取当前语言
        current_language = getattr(request.state, 'language', 'en-US')
        switch_urls = create_language_switcher_links(request)
        
        return {
            "success": True,
            "data": {
                "currentLanguage": current_language,
                "switchUrls": switch_urls
            }
        }
    except Exception as e:
        # 返回错误信息而不是抛出异常
        return {
            "success": False,
            "error": f"Failed to get language switcher links: {str(e)}",
            "data": {
                "currentLanguage": "en-US",
                "switchUrls": {
                    "en-US": "/",
                    "zh-CN": "/zh-cn/"
                }
            }
        }


# Welcome message state file path
WELCOME_STATE_FILE = Path("data") / "welcome_dismissed.json"


def _get_welcome_state():
    """Get welcome message dismissed state"""
    try:
        if WELCOME_STATE_FILE.exists():
            with open(WELCOME_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('dismissed', False)
        return False
    except Exception:
        return False


def _set_welcome_dismissed():
    """Set welcome message as dismissed"""
    try:
        # Ensure data directory exists
        WELCOME_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(WELCOME_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'dismissed': True}, f)
        return True
    except Exception:
        return False


@router.get("/welcome-message/status")
async def get_welcome_message_status():
    """
    Check if welcome message should be displayed

    Returns:
        - dismissed: Whether the welcome message has been dismissed globally
    """
    dismissed = _get_welcome_state()
    return {
        "success": True,
        "data": {
            "dismissed": dismissed
        }
    }


@router.post("/welcome-message/dismiss")
async def dismiss_welcome_message():
    """
    Mark welcome message as dismissed globally

    Once dismissed by any user, it will not be shown to anyone again.
    """
    success = _set_welcome_dismissed()

    if success:
        return {
            "success": True,
            "message": "Welcome message dismissed successfully"
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to dismiss welcome message"
        )

