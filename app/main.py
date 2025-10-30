import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.openapi.utils import get_openapi
from app.config import settings, get_cors_origins_list
from app.routers import email, system, admin, pattern
from app.services.storage_service import storage_service
from app.services.log_service import log_service, LogLevel, LogType


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


# 自定义OpenAPI配置
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="Temporary Email Service",
        version="1.0.0",
        description="自动生成临时邮箱并接收验证码的API服务",
        routes=app.routes,
    )
    
    # 设置语言为简体中文
    openapi_schema["info"]["x-logo"] = {
        "url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

# 创建FastAPI应用
app = FastAPI(
    title="Temporary Email Service",
    description="自动生成临时邮箱并接收验证码的API服务",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,  # 禁用默认的 docs URL
    redoc_url=None,  # 禁用默认的 redoc URL
    openapi_url="/openapi.json",
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

# 设置自定义OpenAPI
app.openapi = custom_openapi

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

# 註冊路由
app.include_router(email.router)
app.include_router(system.router)
app.include_router(admin.router)
app.include_router(pattern.router)

# 自定义Docs页面 - 使用简体中文
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """自定义Swagger UI页面 - 简体中文版本"""
    return FileResponse("static/docs-zh-cn.html")

# 自定义ReDoc页面 - 使用简体中文
@app.get("/redoc", include_in_schema=False)
async def custom_redoc_html():
    """自定义ReDoc页面 - 简体中文版本"""
    return FileResponse("static/redoc-zh-cn.html")

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
