#!/usr/bin/env python3
"""运行脚本"""
import sys
import uvicorn
from app.config import settings

if __name__ == "__main__":
    # 检查命令行参数
    debug_mode = "--debug" in sys.argv

    # 如果启用 debug 模式,设置环境变量
    if debug_mode:
        import os
        os.environ["DEBUG_EMAIL_FETCH"] = "true"
        settings.debug_email_fetch = True
        print("🐛 Debug mode enabled - detailed logs will be shown")

    print("=" * 50)
    print("🚀 Dog love - Temporary Email Service")
    print("=" * 50)
    print(f"📍 Server: http://{settings.host}:{settings.port}")
    print(f"📚 API Docs: http://{settings.host}:{settings.port}/docs")
    print(f"📖 ReDoc: http://{settings.host}:{settings.port}/redoc")
    print(f"🛠️ Admin: http://{settings.host}:{settings.port}/admin")
    print(f"📜 Logs Viewer: http://{settings.host}:{settings.port}/static/logs")

    if debug_mode:
        print(f"🐛 Debug: ON - Email fetch debug logs enabled")
    else:
        print(f"💡 Tip: Use 'python run.py --debug' to enable debug logs")

    print("=" * 50)

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level="info",
    )
