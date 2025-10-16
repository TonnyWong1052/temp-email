"""
實時日誌服務
支援 SSE 串流、日誌過濾和歷史記錄
支援文件日誌持久化（每日輪換）
"""

import asyncio
import os
import logging
import logging.handlers
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Set
from enum import Enum
import json
from collections import deque


class LogLevel(str, Enum):
    """日誌級別"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


class LogType(str, Enum):
    """日誌類型"""
    REQUEST = "request"        # HTTP 請求
    RESPONSE = "response"      # HTTP 響應
    EMAIL_GEN = "email_gen"    # 生成郵箱
    EMAIL_FETCH = "email_fetch"  # 獲取郵件
    CODE_EXTRACT = "code_extract"  # 提取驗證碼
    LLM_CALL = "llm_call"      # LLM 調用
    KV_ACCESS = "kv_access"    # Cloudflare KV 訪問
    SYSTEM = "system"          # 系統事件
    ERROR = "error"            # 錯誤事件


class LogEntry:
    """日誌條目"""
    def __init__(
        self,
        level: LogLevel,
        log_type: LogType,
        message: str,
        details: Optional[Dict] = None,
        duration_ms: Optional[float] = None
    ):
        self.timestamp = datetime.now()
        self.level = level
        self.log_type = log_type
        self.message = message
        self.details = details or {}
        self.duration_ms = duration_ms

    def to_dict(self) -> Dict:
        """轉換為字典"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "type": self.log_type.value,
            "message": self.message,
            "details": self.details,
            "duration_ms": self.duration_ms,
        }

    def to_json(self) -> str:
        """轉換為 JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False)


class LogService:
    """日誌服務（內存 + 文件持久化）"""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.history: deque = deque(maxlen=max_history)
        self.subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        
        # 文件日誌配置
        self.file_logger: Optional[logging.Logger] = None
        self.log_dir: Optional[Path] = None
        self._setup_file_logging()

    def _setup_file_logging(self):
        """設置文件日誌（每日輪換）"""
        try:
            from app.config import settings
            
            if not settings.enable_file_logging:
                return
            
            # 創建日誌目錄
            self.log_dir = Path(settings.log_file_path)
            self.log_dir.mkdir(exist_ok=True)
            
            # 創建 logger
            self.file_logger = logging.getLogger("temp_email_service")
            self.file_logger.setLevel(logging.DEBUG)
            
            # 移除已有的 handlers（避免重複）
            self.file_logger.handlers.clear()
            
            # 應用日誌：每日輪換
            app_log_file = self.log_dir / "app.log"
            app_handler = logging.handlers.TimedRotatingFileHandler(
                filename=str(app_log_file),
                when="midnight",
                interval=1,
                backupCount=settings.log_retention_days,
                encoding="utf-8"
            )
            app_handler.setLevel(logging.DEBUG)
            
            # 錯誤日誌：單獨文件
            error_log_file = self.log_dir / "error.log"
            error_handler = logging.handlers.TimedRotatingFileHandler(
                filename=str(error_log_file),
                when="midnight",
                interval=1,
                backupCount=settings.log_retention_days,
                encoding="utf-8"
            )
            error_handler.setLevel(logging.ERROR)
            
            # 格式化器
            formatter = logging.Formatter(
                '[%(asctime)s] [%(levelname)s] [%(log_type)s] %(message)s | %(details)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            app_handler.setFormatter(formatter)
            error_handler.setFormatter(formatter)
            
            self.file_logger.addHandler(app_handler)
            self.file_logger.addHandler(error_handler)
            
            print(f"📝 File logging enabled: {self.log_dir.absolute()}")
            
        except Exception as e:
            print(f"❌ Failed to setup file logging: {e}")
            self.file_logger = None

    def _write_to_file(self, entry: LogEntry):
        """寫入日誌到文件（同步，非阻塞）"""
        if not self.file_logger:
            return
        
        try:
            # 轉換級別
            level_map = {
                LogLevel.DEBUG: logging.DEBUG,
                LogLevel.INFO: logging.INFO,
                LogLevel.WARNING: logging.WARNING,
                LogLevel.ERROR: logging.ERROR,
                LogLevel.SUCCESS: logging.INFO,
            }
            
            log_level = level_map.get(entry.level, logging.INFO)
            
            # 格式化 details
            details_str = json.dumps(entry.details, ensure_ascii=False) if entry.details else "{}"
            
            # 寫入（帶額外字段）
            self.file_logger.log(
                log_level,
                entry.message,
                extra={
                    'log_type': entry.log_type.value,
                    'details': details_str,
                    'duration_ms': entry.duration_ms or 0
                }
            )
        except Exception as e:
            # 避免日誌記錄失敗影響主流程
            print(f"⚠️ File logging error: {e}")

    async def log(
        self,
        level: LogLevel,
        log_type: LogType,
        message: str,
        details: Optional[Dict] = None,
        duration_ms: Optional[float] = None
    ):
        """記錄日誌（內存 + 文件）"""
        entry = LogEntry(level, log_type, message, details, duration_ms)

        async with self._lock:
            # 添加到內存歷史記錄
            self.history.append(entry)
            
            # 寫入文件（在鎖外執行，避免阻塞）
            asyncio.create_task(asyncio.to_thread(self._write_to_file, entry))

            # 廣播給所有訂閱者
            dead_subscribers = set()
            for queue in self.subscribers:
                try:
                    await asyncio.wait_for(queue.put(entry), timeout=1.0)
                except (asyncio.TimeoutError, asyncio.QueueFull):
                    # 訂閱者處理太慢，標記為移除
                    dead_subscribers.add(queue)
                except Exception:
                    dead_subscribers.add(queue)

            # 移除失效的訂閱者
            self.subscribers -= dead_subscribers

    async def subscribe(self) -> asyncio.Queue:
        """訂閱日誌流"""
        queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self.subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue):
        """取消訂閱"""
        async with self._lock:
            self.subscribers.discard(queue)

    def get_history(
        self,
        levels: Optional[List[LogLevel]] = None,
        types: Optional[List[LogType]] = None,
        keyword: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        獲取歷史日誌（帶過濾）

        Args:
            levels: 過濾的日誌級別列表
            types: 過濾的日誌類型列表
            keyword: 關鍵字搜索（在 message 和 details 中）
            limit: 最大返回數量
        """
        filtered = []

        # 從最新往舊遍歷
        for entry in reversed(self.history):
            # 過濾級別
            if levels and entry.level not in levels:
                continue

            # 過濾類型
            if types and entry.log_type not in types:
                continue

            # 過濾關鍵字
            if keyword:
                keyword_lower = keyword.lower()
                if keyword_lower not in entry.message.lower():
                    # 檢查 details 中是否包含關鍵字
                    details_str = json.dumps(entry.details, ensure_ascii=False).lower()
                    if keyword_lower not in details_str:
                        continue

            filtered.append(entry.to_dict())

            if len(filtered) >= limit:
                break

        return filtered

    def clear_history(self):
        """清空歷史記錄"""
        self.history.clear()

    async def get_stats(self) -> Dict:
        """獲取統計信息"""
        try:
            async with self._lock:
                total = len(self.history)

                # 統計各級別數量
                level_counts = {}
                for level in LogLevel:
                    try:
                        level_counts[level.value] = sum(
                            1 for entry in self.history if entry.level == level
                        )
                    except Exception as e:
                        # 單個級別統計失敗，記錄並繼續
                        print(f"⚠️ 統計級別 {level.value} 失敗: {e}")
                        level_counts[level.value] = 0

                # 統計各類型數量
                type_counts = {}
                for log_type in LogType:
                    try:
                        type_counts[log_type.value] = sum(
                            1 for entry in self.history if entry.log_type == log_type
                        )
                    except Exception as e:
                        # 單個類型統計失敗，記錄並繼續
                        print(f"⚠️ 統計類型 {log_type.value} 失敗: {e}")
                        type_counts[log_type.value] = 0

                # 統計獨立IP數量
                unique_ips = set()
                try:
                    for entry in self.history:
                        if entry.details and 'client_ip' in entry.details:
                            ip = entry.details['client_ip']
                            if ip and ip != 'unknown':
                                unique_ips.add(ip)
                except Exception as e:
                    # IP 統計失敗，記錄但返回空集合
                    print(f"⚠️ 統計獨立 IP 失敗: {e}")
                    unique_ips = set()

                return {
                    "total": total,
                    "subscribers": len(self.subscribers),
                    "level_counts": level_counts,
                    "type_counts": type_counts,
                    "unique_ips": len(unique_ips),
                }
        except Exception as e:
            # 捕獲所有異常，記錄詳細錯誤
            import traceback
            error_detail = traceback.format_exc()
            print(f"❌ 獲取日誌統計失敗: {str(e)}")
            print(f"完整錯誤堆棧:\n{error_detail}")

            # 返回空統計，避免整個服務失敗
            return {
                "total": 0,
                "subscribers": 0,
                "level_counts": {},
                "type_counts": {},
                "unique_ips": 0,
                "error": str(e),
                "error_detail": error_detail
            }


# 全局單例
log_service = LogService()
