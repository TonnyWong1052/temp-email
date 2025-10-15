"""
簡單的應用層緩存服務
用於減少 Cloudflare Workers KV 的讀取次數
"""

import time
from typing import Dict, Optional, Any, Tuple


class SimpleCache:
    """
    簡單的 TTL 緩存實現
    """

    def __init__(self):
        self._cache: Dict[str, Tuple[Any, float]] = {}  # key -> (value, expire_time)

    def get(self, key: str) -> Optional[Any]:
        """
        獲取緩存值

        Args:
            key: 緩存鍵

        Returns:
            緩存值或 None（如果不存在或已過期）
        """
        if key not in self._cache:
            return None

        value, expire_time = self._cache[key]

        # 檢查是否過期
        if time.time() > expire_time:
            del self._cache[key]
            return None

        return value

    def set(self, key: str, value: Any, ttl: int = 60):
        """
        設置緩存值

        Args:
            key: 緩存鍵
            value: 緩存值
            ttl: 過期時間（秒）
        """
        expire_time = time.time() + ttl
        self._cache[key] = (value, expire_time)

    def delete(self, key: str):
        """
        刪除緩存

        Args:
            key: 緩存鍵
        """
        if key in self._cache:
            del self._cache[key]

    def clear(self):
        """清空所有緩存"""
        self._cache.clear()

    def cleanup_expired(self):
        """
        清理已過期的緩存條目
        """
        current_time = time.time()
        expired_keys = [
            key
            for key, (_, expire_time) in self._cache.items()
            if current_time > expire_time
        ]

        for key in expired_keys:
            del self._cache[key]

    def get_stats(self) -> Dict[str, int]:
        """
        獲取緩存統計信息

        Returns:
            統計信息字典
        """
        current_time = time.time()
        active_count = sum(
            1 for _, expire_time in self._cache.values() if current_time <= expire_time
        )

        return {
            "total_entries": len(self._cache),
            "active_entries": active_count,
            "expired_entries": len(self._cache) - active_count,
        }


# 全局緩存實例
# 郵件索引緩存 (TTL: 30 秒)
mail_index_cache = SimpleCache()

# 郵件內容緩存 (TTL: 5 分鐘)
mail_content_cache = SimpleCache()
