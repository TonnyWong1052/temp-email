"""
实时日志服务
支持 SSE 流、日志过滤和历史记录
支持文件日志持久化（每日轮换）
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
    """日志级别"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


class LogType(str, Enum):
    """日志类型"""
    REQUEST = "request"        # HTTP 请求
    RESPONSE = "response"      # HTTP 响应
    EMAIL_GEN = "email_gen"    # 生成邮箱
    EMAIL_FETCH = "email_fetch"  # 获取邮件
    CODE_EXTRACT = "code_extract"  # 提取验证码
    LLM_CALL = "llm_call"      # LLM 调用
    KV_ACCESS = "kv_access"    # Cloudflare KV 访问
    SYSTEM = "system"          # 系统事件
    ERROR = "error"            # 错误事件


class LogEntry:
    """日志条目"""
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
        """转换为字典"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "type": self.log_type.value,
            "message": self.message,
            "details": self.details,
            "duration_ms": self.duration_ms,
        }

    def to_json(self) -> str:
        """转换为 JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False)


class LogService:
    """日志服务（内存 + 文件持久化）"""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.history: deque = deque(maxlen=max_history)
        self.subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        # 抽样计数器（降低 INFO/SUCCESS 级别的 I/O）
        self._info_counter = 0
        self._success_counter = 0
        
        # 文件日誌配置
        self.file_logger: Optional[logging.Logger] = None
        self.json_logger: Optional[logging.Logger] = None
        self.log_dir: Optional[Path] = None
        self._setup_file_logging()

    def _setup_file_logging(self):
        """设置文件日志（每日轮换）"""
        try:
            from app.config import settings
            
            if not settings.enable_file_logging:
                return
            
            # 创建日志目录
            self.log_dir = Path(settings.log_file_path)
            self.log_dir.mkdir(exist_ok=True)
            
            # 创建 TEXT logger（可选）
            self.file_logger = logging.getLogger("temp_email_service")
            self.file_logger.setLevel(logging.DEBUG)
            
            # 移除已有的 handlers（避免重复）
            self.file_logger.handlers.clear()
            
            if getattr(settings, "enable_text_file_logging", True):
                # 应用日志：每日轮换（文本格式）
                app_log_file = self.log_dir / "app.log"
                app_handler = logging.handlers.TimedRotatingFileHandler(
                    filename=str(app_log_file),
                    when="midnight",
                    interval=1,
                    backupCount=settings.log_retention_days,
                    encoding="utf-8"
                )
                app_handler.setLevel(logging.DEBUG)

                # 错误日志：单独文件（文本格式）
                error_log_file = self.log_dir / "error.log"
                error_handler = logging.handlers.TimedRotatingFileHandler(
                    filename=str(error_log_file),
                    when="midnight",
                    interval=1,
                    backupCount=settings.log_retention_days,
                    encoding="utf-8"
                )
                error_handler.setLevel(logging.ERROR)

                text_formatter = logging.Formatter(
                    '[%(asctime)s] [%(levelname)s] [%(log_type)s] %(message)s | %(details)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
                app_handler.setFormatter(text_formatter)
                error_handler.setFormatter(text_formatter)

                self.file_logger.addHandler(app_handler)
                self.file_logger.addHandler(error_handler)

            # 创建 JSON logger（可选；便于 ELK/云端日志采集）
            if getattr(settings, "enable_json_file_logging", True):
                self.json_logger = logging.getLogger("temp_email_service_json")
                self.json_logger.setLevel(logging.DEBUG)
                self.json_logger.handlers.clear()

                app_json_file = self.log_dir / "app.jsonl"
                app_json_handler = logging.handlers.TimedRotatingFileHandler(
                    filename=str(app_json_file),
                    when="midnight",
                    interval=1,
                    backupCount=settings.log_retention_days,
                    encoding="utf-8"
                )
                app_json_handler.setLevel(logging.DEBUG)

                error_json_file = self.log_dir / "error.jsonl"
                error_json_handler = logging.handlers.TimedRotatingFileHandler(
                    filename=str(error_json_file),
                    when="midnight",
                    interval=1,
                    backupCount=settings.log_retention_days,
                    encoding="utf-8"
                )
                error_json_handler.setLevel(logging.ERROR)

                json_formatter = logging.Formatter('%(message)s')
                app_json_handler.setFormatter(json_formatter)
                error_json_handler.setFormatter(json_formatter)

                self.json_logger.addHandler(app_json_handler)
                self.json_logger.addHandler(error_json_handler)
            
            print(f"📝 File logging enabled: {self.log_dir.absolute()}")
            
        except Exception as e:
            print(f"❌ Failed to setup file logging: {e}")
            self.file_logger = None

    def _write_to_file(self, entry: LogEntry):
        """写入日志到文件（同步，非阻塞）"""
        if not self.file_logger:
            return
        
        try:
            # 转换级别
            level_map = {
                LogLevel.DEBUG: logging.DEBUG,
                LogLevel.INFO: logging.INFO,
                LogLevel.WARNING: logging.WARNING,
                LogLevel.ERROR: logging.ERROR,
                LogLevel.SUCCESS: logging.INFO,
            }

            log_level = level_map.get(entry.level, logging.INFO)

            # JSON 内容
            json_payload = entry.to_json()

            # 文本格式 details
            details_str = json.dumps(entry.details, ensure_ascii=False) if entry.details else "{}"

            # TEXT handlers（可选）
            if self.file_logger and self.file_logger.handlers:
                self.file_logger.log(
                    log_level,
                    entry.message,
                    extra={
                        'log_type': entry.log_type.value,
                        'details': details_str,
                        'duration_ms': entry.duration_ms or 0
                    }
                )

            # JSON handlers（可选）
            if self.json_logger and self.json_logger.handlers:
                self.json_logger.log(log_level, json_payload)

        except Exception as e:
            # 避免日志记录失败影响主流程
            print(f"⚠️ File logging error: {e}")

    def _should_sample(self, entry: "LogEntry") -> bool:
        """是否需要抽样丢弃此条日志（仅针对 INFO/SUCCESS）"""
        try:
            from app.config import settings
        except Exception:
            return False

        if entry.level == LogLevel.INFO:
            rate = max(1, int(getattr(settings, "log_info_sample_rate", 1)))
            if rate > 1:
                self._info_counter = (self._info_counter + 1) % rate
                return self._info_counter != 0
        if entry.level == LogLevel.SUCCESS:
            rate = max(1, int(getattr(settings, "log_success_sample_rate", 1)))
            if rate > 1:
                self._success_counter = (self._success_counter + 1) % rate
                return self._success_counter != 0
        return False

    async def log(
        self,
        level: LogLevel,
        log_type: LogType,
        message: str,
        details: Optional[Dict] = None,
        duration_ms: Optional[float] = None
    ):
        """记录日志（内存 + 文件）"""
        entry = LogEntry(level, log_type, message, details, duration_ms)

        # 抽样：在高流量时降低 INFO/SUCCESS 的 I/O 与内存占用
        if self._should_sample(entry):
            return

        async with self._lock:
            # 添加到内存历史记录
            self.history.append(entry)

            # 写入文件（在锁外执行，避免阻塞）
            asyncio.create_task(asyncio.to_thread(self._write_to_file, entry))

            # 广播给所有订阅者
            dead_subscribers = set()
            for queue in self.subscribers:
                try:
                    await asyncio.wait_for(queue.put(entry), timeout=1.0)
                except (asyncio.TimeoutError, asyncio.QueueFull):
                    # 订阅者处理过慢，标记为移除
                    dead_subscribers.add(queue)
                except Exception:
                    dead_subscribers.add(queue)

            # 移除失效的订阅者
            self.subscribers -= dead_subscribers

    async def subscribe(self) -> asyncio.Queue:
        """订阅日志流"""
        queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self.subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue):
        """取消订阅"""
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
        获取历史日志（带过滤）

        Args:
            levels: 过滤的日志级别列表
            types: 过滤的日志类型列表
            keyword: 关键词搜索（在 message 和 details 中）
            limit: 最大返回数量
        """
        filtered = []

        # 从最新往旧遍历
        for entry in reversed(self.history):
            # 过滤级别
            if levels and entry.level not in levels:
                continue

            # 过滤类型
            if types and entry.log_type not in types:
                continue

            # 过滤关键词
            if keyword:
                keyword_lower = keyword.lower()
                if keyword_lower not in entry.message.lower():
                    # 检查 details 中是否包含关键词
                    details_str = json.dumps(entry.details, ensure_ascii=False).lower()
                    if keyword_lower not in details_str:
                        continue

            filtered.append(entry.to_dict())

            if len(filtered) >= limit:
                break

        return filtered

    def clear_history(self):
        """清空历史记录"""
        self.history.clear()

    async def get_stats(self) -> Dict:
        """获取统计信息"""
        try:
            async with self._lock:
                total = len(self.history)

                # 统计各级别数量
                level_counts = {}
                for level in LogLevel:
                    try:
                        level_counts[level.value] = sum(
                            1 for entry in self.history if entry.level == level
                        )
                    except Exception as e:
                        # 单个级别统计失败，记录并继续
                        print(f"⚠️ 统计级别 {level.value} 失败: {e}")
                        level_counts[level.value] = 0

                # 统计各类型数量
                type_counts = {}
                for log_type in LogType:
                    try:
                        type_counts[log_type.value] = sum(
                            1 for entry in self.history if entry.log_type == log_type
                        )
                    except Exception as e:
                        # 单个类型统计失败，记录并继续
                        print(f"⚠️ 统计类型 {log_type.value} 失败: {e}")
                        type_counts[log_type.value] = 0

                # 统计独立 IP 数量
                unique_ips = set()
                try:
                    for entry in self.history:
                        if entry.details and 'client_ip' in entry.details:
                            ip = entry.details['client_ip']
                            if ip and ip != 'unknown':
                                unique_ips.add(ip)
                except Exception as e:
                    # IP 统计失败，记录但返回空集合
                    print(f"⚠️ 统计独立 IP 失败: {e}")
                    unique_ips = set()

                return {
                    "total": total,
                    "subscribers": len(self.subscribers),
                    "level_counts": level_counts,
                    "type_counts": type_counts,
                    "unique_ips": len(unique_ips),
                }
        except Exception as e:
            # 捕获所有异常，记录详细错误
            import traceback
            error_detail = traceback.format_exc()
            print(f"❌ 获取日志统计失败: {str(e)}")
            print(f"完整错误堆栈:\n{error_detail}")

            # 返回空统计，避免整体服务失败
            return {
                "total": 0,
                "subscribers": 0,
                "level_counts": {},
                "type_counts": {},
                "unique_ips": 0,
                "error": str(e),
                "error_detail": error_detail
            }


# 全局单例
log_service = LogService()
