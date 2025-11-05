import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.openapi.utils import get_openapi
from app.config import settings, get_cors_origins_list
from app.routers import email, system, admin, pattern, i18n
from app.services.storage_service import storage_service
from app.services.log_service import log_service, LogLevel, LogType
from app.i18n import I18nMiddleware


# 生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用程序生命周期管理"""
    # 启动时
    print("🚀 Starting Temporary Email Service...")
    await log_service.log(
        level=LogLevel.INFO,
        log_type=LogType.SYSTEM,
        message="Service starting",
        details={
            "port": settings.port,
            "env": "development" if settings.reload else "production"
        }
    )

    try:
        origins = get_cors_origins_list()
        await log_service.log(
            level=LogLevel.INFO,
            log_type=LogType.SYSTEM,
            message="CORS configured",
            details={"allow_origins": origins}
        )
    except Exception:
        await log_service.log(
            level=LogLevel.WARNING,
            log_type=LogType.SYSTEM,
            message="CORS parse failed, fallback to *",
            details={"allow_origins": ["*"]}
        )

    # 初始化 Redis（如果啟用）
    if settings.enable_redis:
        await log_service.log(
            level=LogLevel.INFO,
            log_type=LogType.SYSTEM,
            message="Initializing Redis connection"
        )
        try:
            from app.services.redis_client import redis_client

            connected = await redis_client.connect()
            if connected:
                await log_service.log(
                    level=LogLevel.SUCCESS,
                    log_type=LogType.SYSTEM,
                    message="Redis connected",
                    details={
                        "url": settings.redis_url,
                        "l1_cache_ttl": settings.cache_ttl,
                        "cache_max_size": settings.cache_max_size
                    }
                )
            else:
                await log_service.log(
                    level=LogLevel.WARNING,
                    log_type=LogType.SYSTEM,
                    message="Redis connect failed, fallback to memory"
                )
        except Exception as e:
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.SYSTEM,
                message=f"Redis initialization error: {e}",
                details={"error": str(e)}
            )
    else:
        await log_service.log(
            level=LogLevel.INFO,
            log_type=LogType.SYSTEM,
            message="Redis disabled - using in-memory storage",
            details={"tip": "Enable Redis for 10,000+ concurrent users support"}
        )

    # 启动后台清理任务
    cleanup_task = asyncio.create_task(cleanup_expired_emails())

    await log_service.log(
        level=LogLevel.SUCCESS,
        log_type=LogType.SYSTEM,
        message="Service started",
        details={
            "web": f"http://localhost:{settings.port}",
            "docs": f"http://localhost:{settings.port}/docs"
        }
    )
    # 仅保留关键启动完成打印（其余细节已写入日志）
    print("✅ Service started successfully!")

    yield

    # 关闭时
    print("\n👋 Shutting down...")
    cleanup_task.cancel()

    # 斷開 Redis 連接
    if settings.enable_redis:
        try:
            from app.services.redis_client import redis_client
            await redis_client.disconnect()
            await log_service.log(
                level=LogLevel.INFO,
                log_type=LogType.SYSTEM,
                message="Redis disconnected"
            )
        except Exception as e:
            await log_service.log(
                level=LogLevel.WARNING,
                log_type=LogType.SYSTEM,
                message="Error disconnecting Redis",
                details={"error": str(e)}
            )

    await log_service.log(
        level=LogLevel.INFO,
        log_type=LogType.SYSTEM,
        message="Shutdown complete"
    )


# 后台清理任务
async def cleanup_expired_emails():
    """每5分钟清理一次过期邮箱"""
    while True:
        try:
            await asyncio.sleep(5 * 60)  # 5分钟
            count = storage_service.cleanup_expired()
            if count > 0:
                await log_service.log(
                    level=LogLevel.INFO,
                    log_type=LogType.SYSTEM,
                    message="Expired emails cleaned",
                    details={"count": count}
                )
        except asyncio.CancelledError:
            break
        except Exception as e:
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.SYSTEM,
                message="Cleanup error",
                details={"error": str(e)}
            )


# 自定义OpenAPI配置 - 支持多语言
def custom_openapi(language: str = "zh-CN"):
    """
    生成多语言的 OpenAPI schema

    Args:
        language: 语言代码 (en-US 或 zh-CN)
    """
    from app.i18n.translations import translation_manager

    # 根据语言获取标题和描述
    title = translation_manager.get_translation("api_docs.title", language)
    description = translation_manager.get_translation("api_docs.description", language)

    openapi_schema = get_openapi(
        title=title,
        version="1.0.0",
        description=description,
        routes=app.routes,
    )

    # 为每个端点添加翻译后的描述
    for path, path_item in openapi_schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method in ["get", "post", "put", "delete", "patch"]:
                # 根据操作ID获取翻译
                operation_id = operation.get("operationId", "")

                # 映射操作ID到翻译键
                translation_key_map = {
                    "generate_email_api_email_generate": "generate_email",
                    "get_mails_api_email__token__mails_get": "get_mails",
                    "get_mail_detail_api_email__token__mail__mail_id__get": "get_mail_detail",
                    "get_codes_api_email__token__codes_get": "extract_codes",
                    "wait_for_mail_api_email__token__wait_get": "wait_for_mail",
                    "get_domains_api_domains_get": "get_domains",
                    "health_check_api_health_get": "health_check",
                    "test_cloudflare_test_get": "test_cloudflare"
                }

                endpoint_key = translation_key_map.get(operation_id)
                if endpoint_key:
                    summary_key = f"api_docs.endpoints.{endpoint_key}.summary"
                    desc_key = f"api_docs.endpoints.{endpoint_key}.description"

                    summary = translation_manager.get_translation(summary_key, language)
                    desc = translation_manager.get_translation(desc_key, language)

                    # 只有在翻译存在时才更新（避免显示翻译键）
                    if summary and summary != summary_key:
                        operation["summary"] = summary
                    if desc and desc != desc_key:
                        operation["description"] = desc

                    # 翻译参数描述
                    if "parameters" in operation:
                        for param in operation["parameters"]:
                            param_name = param.get("name", "")
                            param_key = f"api_docs.endpoints.{endpoint_key}.params.{param_name}"
                            param_desc = translation_manager.get_translation(param_key, language)
                            if param_desc and param_desc != param_key:
                                param["description"] = param_desc

    # 设置 logo
    openapi_schema["info"]["x-logo"] = {
        "url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"
    }

    return openapi_schema

# 创建FastAPI应用
app = FastAPI(
    title="Temporary Email Service",
    description="自动生成临时邮箱并接收验证码的API服务",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,  # 禁用默认的 docs URL
    redoc_url=None,  # 禁用默认的 redoc URL
    openapi_url=None,  # 禁用默认的 openapi URL，使用自定义多语言端点
    swagger_ui_parameters={
        "deepLinking": True,
        "displayRequestDuration": True,
        "docExpansion": "none",
        "operationsSorter": "alpha",
        "filter": True,
        "tryItOutEnabled": True,
        "supportedSubmitMethods": ["get", "post", "put", "delete"],
        "persistAuthorization": False,
        "displayOperationId": False,
        "showExtensions": True,
        "showCommonExtensions": True,
        "tryItOutEnabled": True,
    },
)

# CORS中間件
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 日誌中間件
from app.middleware import LoggingMiddleware
app.add_middleware(LoggingMiddleware)

# i18n 中間件 (必須在日誌中間件之後)
app.add_middleware(I18nMiddleware, fallback_language="en-US")

# 註冊路由
app.include_router(email.router)
app.include_router(system.router)
app.include_router(admin.router)
app.include_router(pattern.router)
app.include_router(i18n.router)

# OpenAPI JSON 端点 - 多语言支持
@app.get("/openapi.json", include_in_schema=False)
async def get_openapi_json_zh():
    """OpenAPI JSON - 简体中文版本（默认）"""
    return custom_openapi("zh-CN")

@app.get("/zh-cn/openapi.json", include_in_schema=False)
async def get_openapi_json_zh_cn():
    """OpenAPI JSON - 简体中文版本"""
    return custom_openapi("zh-CN")

@app.get("/en/openapi.json", include_in_schema=False)
async def get_openapi_json_en():
    """OpenAPI JSON - English version"""
    return custom_openapi("en-US")

# 自定义Docs页面 - 多语言支持（带语言切换器）
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """自定义Swagger UI页面 - 带语言切换器（默认简体中文）"""
    return FileResponse("static/swagger-ui.html")

@app.get("/zh-cn/docs", include_in_schema=False)
async def custom_swagger_ui_html_zh():
    """自定义Swagger UI页面 - 简体中文版本"""
    return FileResponse("static/swagger-ui.html")

@app.get("/en/docs", include_in_schema=False)
async def custom_swagger_ui_html_en():
    """Custom Swagger UI page - English version"""
    return FileResponse("static/swagger-ui.html")

# 自定义ReDoc页面 - 多语言支持
@app.get("/redoc", include_in_schema=False)
async def custom_redoc_html():
    """自定义ReDoc页面 - 简体中文版本（默认）"""
    from fastapi.openapi.docs import get_redoc_html
    return get_redoc_html(
        openapi_url="/openapi.json",
        title="API文档 - 临时邮箱服务",
        redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png"
    )

@app.get("/zh-cn/redoc", include_in_schema=False)
async def custom_redoc_html_zh():
    """自定义ReDoc页面 - 简体中文版本"""
    from fastapi.openapi.docs import get_redoc_html
    return get_redoc_html(
        openapi_url="/zh-cn/openapi.json",
        title="API文档 - 临时邮箱服务",
        redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png"
    )

@app.get("/en/redoc", include_in_schema=False)
async def custom_redoc_html_en():
    """Custom ReDoc page - English version"""
    from fastapi.openapi.docs import get_redoc_html
    return get_redoc_html(
        openapi_url="/en/openapi.json",
        title="API Documentation - Temporary Email Service",
        redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png"
    )

# 根路径
@app.get("/")
async def root():
    """首页 - 返回Web界面"""
    try:
        return FileResponse("static/index.html")
    except Exception:
        return {
            "message": "Temporary Email Service API",
            "docs": "/docs",
            "health": "/api/health",
        }

# 英文路由
@app.get("/en/")
async def root_en():
    """英文首页 - 返回Web界面"""
    try:
        response = FileResponse("static/index.html")
        response.headers["Content-Language"] = "en-US"
        return response
    except Exception:
        return {
            "message": "Temporary Email Service API",
            "docs": "/docs",
            "health": "/api/health",
        }

# 简体中文路由
@app.get("/zh-cn/")
async def root_zh_cn():
    """简体中文首页 - 返回Web界面"""
    try:
        response = FileResponse("static/index.html")
        response.headers["Content-Language"] = "zh-CN"
        return response
    except Exception:
        return {
            "message": "Temporary Email Service API",
            "docs": "/docs",
            "health": "/api/health",
        }


# 静态文件 (Web界面) - 必须在特定路由之后挂载
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception:
    pass  # 静态文件目录不存在时跳过


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level="info",
    )
