"""
Cache Manager with L1/L2 dual-layer caching and Request Coalescing

Features:
1. L1 Cache: 30s - Low latency
2. L2 Cache: 5min - Backup when API fails
3. Request Coalescing: Prevent duplicate API calls
4. Auto-refresh: Refresh cache on errors
"""

import asyncio
import json
import logging
import time
from typing import List, Optional, Callable, Any
from datetime import datetime, timedelta
from app.models import Mail
from app.services.redis_client import redis_client
from app.config import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """Cache Manager"""

    def __init__(self):
        self.cache_prefix = "cache:mails:"  # Cache key prefix
        self.l1_ttl = settings.cache_ttl  # L1 cache TTL
        self.l2_ttl = 300  # L2 cache TTL: 5min
        self.fetching_locks = {}  # Fetch locks
        self.fetching_results = {}  # Fetch results cache

    async def get_or_fetch_mails(
        self,
        email: str,
        fetch_func: Callable,
        force_refresh: bool = False
    ) -> tuple[List[Mail], bool]:
        """
        Get mails from cache or fetch from API

        Args:
            email: Email address
            fetch_func: Function to fetch mails
            force_refresh: Force refresh cache

        Returns:
            (mails, from_cache): Mails list and whether from cache
        """
        cache_key = f"{self.cache_prefix}{email}"
        debug = bool(getattr(settings, "debug_email_fetch", False))

        if debug:
            logger.info(f"[Cache Manager] get_or_fetch_mails for: {email}")

        # If not forced refresh, try L1 cache first
        if not force_refresh:
            cached_data = await self._get_from_cache(cache_key, level="L1")
            if cached_data:
                if debug:
                    logger.info(f"[Cache Manager] L1 Cache HIT for {email}")
                return cached_data["mails"], True

        # L1 cache miss, check if another request is already fetching
        if email in self.fetching_locks:
            if debug:
                logger.info(f"[Cache Manager] Another request is fetching, waiting...")

            # Wait for the other request to complete (max 3 seconds)
            for _ in range(30):
                await asyncio.sleep(0.1)
                if email in self.fetching_results:
                    result = self.fetching_results.pop(email)
                    if debug:
                        logger.info(f"[Cache Manager] Coalesced request result")
                    return result, True

        # Set fetch lock
        self.fetching_locks[email] = True

        try:
            # Fetch from API
            if debug:
                logger.info(f"[Cache Manager] Fetching from API...")

            start_time = time.time()
            mails = await fetch_func(email)
            duration = time.time() - start_time

            if debug:
                logger.info(f"[Cache Manager] API returned {len(mails)} mails in {duration:.2f}s")

            # Save to cache
            await self._save_to_cache(cache_key, mails)

            # Cache result for other waiting requests
            self.fetching_results[email] = mails

            return mails, False

        except Exception as e:
            logger.error(f"[Cache Manager] API fetch failed: {str(e)}")

            # If API fails, try L2 cache
            cached_data = await self._get_from_cache(cache_key, level="L2")
            if cached_data:
                logger.warning(f"[Cache Manager] API failed, using L2 cache for {email}")
                return cached_data["mails"], True

            # No cache available, return empty
            logger.error(f"[Cache Manager] No cache available for {email}")
            return [], False

        finally:
            # Release lock
            self.fetching_locks.pop(email, None)

            # Cleanup fetch result after 1 second
            asyncio.create_task(self._cleanup_fetch_result(email))

    async def _get_from_cache(
        self,
        cache_key: str,
        level: str = "L1"
    ) -> Optional[dict]:
        """
        Get data from cache

        Args:
            cache_key: Cache key
            level: Cache level (L1 or L2)

        Returns:
            Cache data with mails and cached_at, or None
        """
        try:
            # Get from Redis
            full_key = f"{cache_key}:{level}"
            data = await redis_client.get(full_key)

            if not data:
                return None

            # Parse JSON
            cached_obj = json.loads(data)

            # Check cache expiration
            cached_at = datetime.fromisoformat(cached_obj["cached_at"])
            ttl = self.l1_ttl if level == "L1" else self.l2_ttl
            expires_at = cached_at + timedelta(seconds=ttl)

            if datetime.now() > expires_at:
                # Cache expired
                return None

            # Parse mail objects
            from app.models import Code

            mails = []
            for mail_dict in cached_obj["mails"]:
                codes = [
                    Code(
                        code=c["code"],
                        type=c["type"],
                        length=c["length"],
                        confidence=c["confidence"],
                        pattern=c.get("pattern", ""),
                    )
                    for c in mail_dict.get("codes", [])
                ]

                mail = Mail(
                    id=mail_dict["id"],
                    from_=mail_dict["from_"],
                    to=mail_dict.get("to", ""),
                    subject=mail_dict["subject"],
                    content=mail_dict["content"],
                    html_content=mail_dict.get("html_content"),
                    received_at=datetime.fromisoformat(mail_dict["received_at"]),
                    read=mail_dict.get("read", False),
                    email_token=mail_dict.get("email_token"),
                    codes=codes if codes else None,
                )
                mails.append(mail)

            return {
                "mails": mails,
                "cached_at": cached_at,
            }

        except Exception as e:
            logger.error(f"[Cache Manager] Failed to get from cache: {str(e)}")
            return None

    async def _save_to_cache(self, cache_key: str, mails: List[Mail]) -> bool:
        """
        Save to L1 and L2 cache

        Args:
            cache_key: Cache key
            mails: Mail list

        Returns:
            Success or not
        """
        try:
            # Serialize mails
            mails_data = [
                {
                    "id": m.id,
                    "from_": m.from_,
                    "to": m.to,
                    "subject": m.subject,
                    "content": m.content,
                    "html_content": m.html_content,
                    "received_at": m.received_at.isoformat(),
                    "read": m.read,
                    "email_token": m.email_token,
                    "codes": [
                        {
                            "code": c.code,
                            "type": c.type,
                            "length": c.length,
                            "confidence": c.confidence,
                            "pattern": c.pattern,
                        }
                        for c in (m.codes or [])
                    ],
                }
                for m in mails
            ]

            cached_obj = {
                "mails": mails_data,
                "cached_at": datetime.now().isoformat(),
            }

            cached_json = json.dumps(cached_obj)

            # Save to L1 cache (30s)
            l1_key = f"{cache_key}:L1"
            await redis_client.setex(l1_key, self.l1_ttl, cached_json)

            # Save to L2 cache (5min)
            l2_key = f"{cache_key}:L2"
            await redis_client.setex(l2_key, self.l2_ttl, cached_json)

            return True

        except Exception as e:
            logger.error(f"[Cache Manager] Failed to save to cache: {str(e)}")
            return False

    async def _cleanup_fetch_result(self, email: str):
        """Clean up fetch result cache"""
        await asyncio.sleep(1)
        self.fetching_results.pop(email, None)

    async def invalidate_cache(self, email: str) -> bool:
        """
        Invalidate cache

        Args:
            email: Email address

        Returns:
            Success or not
        """
        try:
            cache_key = f"{self.cache_prefix}{email}"
            l1_key = f"{cache_key}:L1"
            l2_key = f"{cache_key}:L2"

            await redis_client.delete(l1_key, l2_key)

            logger.info(f"[Cache Manager] Invalidated cache for {email}")
            return True

        except Exception as e:
            logger.error(f"[Cache Manager] Failed to invalidate cache: {str(e)}")
            return False

    async def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        try:
            pattern = f"{self.cache_prefix}*"
            cursor = 0
            total_cached = 0

            # Scan all cache keys
            while True:
                cursor, keys = await redis_client.redis.scan(
                    cursor=cursor, match=pattern, count=100
                )
                total_cached += len(keys)

                if cursor == 0:
                    break

            return {
                "total_cached_emails": total_cached // 2,  # Divide by 2 for L1 and L2
                "l1_ttl": self.l1_ttl,
                "l2_ttl": self.l2_ttl,
                "active_fetching": len(self.fetching_locks),
            }

        except Exception as e:
            logger.error(f"[Cache Manager] Failed to get stats: {str(e)}")
            return {}


# Global cache manager instance
cache_manager = CacheManager()
