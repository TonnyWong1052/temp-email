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


# 生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用程序生命周期管理"""
    # 启动时
    print("🚀 Starting Temporary Email Service...")
    try:
        origins = get_cors_origins_list()
        print(f"✅ CORS allow_origins: {origins}")
    except Exception:
        print("✅ CORS allow_origins: ['*'] (fallback)")

    # 启动后台清理任务
    cleanup_task = asyncio.create_task(cleanup_expired_emails())

    yield

    # 关闭时
    cleanup_task.cancel()
    print("👋 Shutting down...")


# 后台清理任务
async def cleanup_expired_emails():
    """每5分钟清理一次过期邮箱"""
    while True:
        try:
            await asyncio.sleep(5 * 60)  # 5分钟
            count = storage_service.cleanup_expired()
            if count > 0:
                print(f"🧹 Cleaned up {count} expired emails")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"❌ Cleanup error: {e}")


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
