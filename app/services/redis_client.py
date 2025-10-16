"""
Redis 客戶端連接管理器
提供 Redis 連接池和基礎操作方法
"""
import redis.asyncio as redis
from typing import Optional
from app.config import settings


class RedisClient:
    """Redis 客戶端管理器"""
    
    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._enabled = False
    
    async def connect(self) -> bool:
        """建立 Redis 連接"""
        try:
            enable_redis = getattr(settings, "enable_redis", False)

            if not enable_redis:
                print("[Redis] Redis is disabled in configuration")
                return False

            redis_url = getattr(settings, "redis_url", "redis://localhost:6379/0")

            self._redis = redis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50,  # 連接池大小
                socket_connect_timeout=5,
                socket_keepalive=True,
            )

            # 測試連接
            await self._redis.ping()
            self._enabled = True
            print(f"[Redis] ✅ Connected to Redis: {redis_url}")
            return True

        except Exception as e:
            print(f"[Redis] ❌ Failed to connect: {e}")
            print("[Redis] Falling back to in-memory storage")
            self._redis = None
            self._enabled = False
            return False
    
    async def disconnect(self) -> None:
        """關閉 Redis 連接"""
        if self._redis:
            await self._redis.close()
            self._enabled = False
            print("[Redis] Disconnected")
    
    @property
    def is_enabled(self) -> bool:
        """檢查 Redis 是否可用"""
        return self._enabled and self._redis is not None
    
    @property
    def client(self) -> Optional[redis.Redis]:
        """獲取 Redis 客戶端實例"""
        return self._redis if self.is_enabled else None

    # 向後兼容：提供 .redis 屬性供現有代碼使用（如 scan 調用）
    @property
    def redis(self) -> Optional[redis.Redis]:
        return self.client
    
    async def get(self, key: str) -> Optional[str]:
        """獲取值"""
        if not self.is_enabled:
            return None
        try:
            return await self._redis.get(key)
        except Exception as e:
            print(f"[Redis] GET error: {e}")
            return None
    
    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """設置值（支持過期時間）"""
        if not self.is_enabled:
            return False
        try:
            await self._redis.set(key, value, ex=ex)
            return True
        except Exception as e:
            print(f"[Redis] SET error: {e}")
            return False

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        """設置值並指定過期時間（秒），與 redis-py 的 setex 對齊"""
        if not self.is_enabled:
            return False
        try:
            # redis-py 提供 setex(name, time, value)
            await self._redis.setex(key, seconds, value)
            return True
        except Exception as e:
            print(f"[Redis] SETEX error: {e}")
            return False
    
    async def delete(self, *keys: str) -> int:
        """刪除一個或多個鍵，返回實際刪除數量"""
        if not self.is_enabled:
            return 0
        try:
            # 允許傳入可迭代參數（保守處理）
            if len(keys) == 1 and isinstance(keys[0], (list, tuple, set)):
                keys = tuple(keys[0])  # type: ignore
            return await self._redis.delete(*keys)
        except Exception as e:
            print(f"[Redis] DELETE error: {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """檢查鍵是否存在"""
        if not self.is_enabled:
            return False
        try:
            return await self._redis.exists(key) > 0
        except Exception as e:
            print(f"[Redis] EXISTS error: {e}")
            return False
    
    async def expire(self, key: str, seconds: int) -> bool:
        """設置過期時間"""
        if not self.is_enabled:
            return False
        try:
            await self._redis.expire(key, seconds)
            return True
        except Exception as e:
            print(f"[Redis] EXPIRE error: {e}")
            return False
    
    async def ttl(self, key: str) -> int:
        """獲取剩餘生存時間（秒）"""
        if not self.is_enabled:
            return -1
        try:
            return await self._redis.ttl(key)
        except Exception as e:
            print(f"[Redis] TTL error: {e}")
            return -1
    
    async def keys(self, pattern: str = "*") -> list:
        """獲取匹配的鍵列表"""
        if not self.is_enabled:
            return []
        try:
            return await self._redis.keys(pattern)
        except Exception as e:
            print(f"[Redis] KEYS error: {e}")
            return []


# 全局單例
redis_client = RedisClient()
