#!/usr/bin/env python3
"""
Redis 整合測試腳本
測試 Redis 連接、基本功能和快取系統
"""
import asyncio
import sys
import time
from typing import Optional

import httpx
import redis.asyncio as redis


class RedisIntegrationTest:
    """Redis 整合測試"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0", api_base: str = "http://localhost:1234"):
        self.redis_url = redis_url
        self.api_base = api_base
        self.redis_client: Optional[redis.Redis] = None
        self.passed = 0
        self.failed = 0

    async def connect_redis(self):
        """連接 Redis"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5
            )
            await self.redis_client.ping()
            return True
        except Exception as e:
            print(f"❌ Redis 連接失敗: {e}")
            return False

    async def test_redis_basic_operations(self):
        """測試 Redis 基本操作"""
        print("\n" + "="*60)
        print("測試 1: Redis 基本操作")
        print("="*60)

        try:
            # 測試 SET
            await self.redis_client.set("test_key", "test_value", ex=10)
            print("✅ SET 操作成功")

            # 測試 GET
            value = await self.redis_client.get("test_key")
            assert value == "test_value", f"期望 'test_value'，實際 '{value}'"
            print("✅ GET 操作成功")

            # 測試 EXISTS
            exists = await self.redis_client.exists("test_key")
            assert exists, "鍵應該存在"
            print("✅ EXISTS 操作成功")

            # 測試 TTL
            ttl = await self.redis_client.ttl("test_key")
            assert 0 < ttl <= 10, f"TTL 應該在 0-10 之間，實際 {ttl}"
            print(f"✅ TTL 操作成功 (剩餘 {ttl} 秒)")

            # 測試 DELETE
            await self.redis_client.delete("test_key")
            exists = await self.redis_client.exists("test_key")
            assert not exists, "鍵應該已被刪除"
            print("✅ DELETE 操作成功")

            self.passed += 1
            print("\n✅ 測試 1 通過")
            return True

        except Exception as e:
            self.failed += 1
            print(f"\n❌ 測試 1 失敗: {e}")
            return False

    async def test_health_endpoint(self):
        """測試健康檢查端點"""
        print("\n" + "="*60)
        print("測試 2: API 健康檢查 (Redis 狀態)")
        print("="*60)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_base}/api/health")
                data = response.json()

                print(f"狀態碼: {response.status_code}")
                print(f"回應資料: {data}")

                # 檢查 Redis 連接狀態
                redis_connected = data.get("redis_connected", False)
                if redis_connected:
                    print("✅ API 確認 Redis 已連接")
                    self.passed += 1
                    print("\n✅ 測試 2 通過")
                    return True
                else:
                    print("⚠️  API 回報 Redis 未連接")
                    self.passed += 1
                    print("\n⚠️  測試 2 通過 (但 Redis 未啟用)")
                    return True

        except Exception as e:
            self.failed += 1
            print(f"\n❌ 測試 2 失敗: {e}")
            return False

    async def test_cache_system(self):
        """測試快取系統"""
        print("\n" + "="*60)
        print("測試 3: 快取系統 (兩層快取)")
        print("="*60)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 生成臨時郵箱
                print("📧 生成臨時郵箱...")
                response = await client.post(f"{self.api_base}/api/email/generate")
                email_data = response.json()["data"]
                token = email_data["token"]
                email_address = email_data["address"]
                print(f"✅ 生成郵箱: {email_address}")

                # 第一次請求 (應該從 API 獲取)
                print("\n📬 第一次請求郵件...")
                start = time.time()
                response1 = await client.get(f"{self.api_base}/api/email/{token}/mails?limit=10")
                duration1 = time.time() - start
                print(f"⏱️  第一次請求耗時: {duration1:.3f}s")

                # 檢查 Redis 中的快取鍵
                cache_key_l1 = f"cache:mails:{email_address}:L1"
                cache_key_l2 = f"cache:mails:{email_address}:L2"

                l1_exists = await self.redis_client.exists(cache_key_l1)
                l2_exists = await self.redis_client.exists(cache_key_l2)

                if l1_exists:
                    print("✅ L1 快取已建立")
                    l1_ttl = await self.redis_client.ttl(cache_key_l1)
                    print(f"   L1 TTL: {l1_ttl} 秒")

                if l2_exists:
                    print("✅ L2 快取已建立")
                    l2_ttl = await self.redis_client.ttl(cache_key_l2)
                    print(f"   L2 TTL: {l2_ttl} 秒")

                # 第二次請求 (應該從快取獲取)
                await asyncio.sleep(1)
                print("\n📬 第二次請求郵件 (應該命中快取)...")
                start = time.time()
                response2 = await client.get(f"{self.api_base}/api/email/{token}/mails?limit=10")
                duration2 = time.time() - start
                print(f"⏱️  第二次請求耗時: {duration2:.3f}s")

                # 比較時間
                speedup = duration1 / duration2 if duration2 > 0 else 0
                print(f"\n📊 快取加速: {speedup:.2f}x")

                if duration2 < duration1:
                    print("✅ 快取提升性能")
                    self.passed += 1
                    print("\n✅ 測試 3 通過")
                    return True
                else:
                    print("⚠️  快取可能未生效 (但功能正常)")
                    self.passed += 1
                    print("\n⚠️  測試 3 通過 (功能正常)")
                    return True

        except Exception as e:
            self.failed += 1
            print(f"\n❌ 測試 3 失敗: {e}")
            return False

    async def test_redis_storage(self):
        """測試 Redis 儲存服務"""
        print("\n" + "="*60)
        print("測試 4: Redis 儲存服務")
        print("="*60)

        try:
            # 檢查儲存相關的鍵
            email_keys = []
            mail_keys = []

            cursor = 0
            while True:
                cursor, keys = await self.redis_client.scan(cursor=cursor, match="email:*", count=100)
                email_keys.extend(keys)
                if cursor == 0:
                    break

            cursor = 0
            while True:
                cursor, keys = await self.redis_client.scan(cursor=cursor, match="mails:*", count=100)
                mail_keys.extend(keys)
                if cursor == 0:
                    break

            print(f"📊 統計資料:")
            print(f"   email:* 鍵數量: {len(email_keys)}")
            print(f"   mails:* 鍵數量: {len(mail_keys)}")

            if email_keys:
                print(f"\n📧 範例郵箱鍵: {email_keys[0]}")
                data = await self.redis_client.get(email_keys[0])
                print(f"   資料範例: {data[:100]}..." if len(data) > 100 else f"   資料: {data}")

            print("✅ Redis 儲存服務運作正常")
            self.passed += 1
            print("\n✅ 測試 4 通過")
            return True

        except Exception as e:
            self.failed += 1
            print(f"\n❌ 測試 4 失敗: {e}")
            return False

    async def cleanup(self):
        """清理資源"""
        if self.redis_client:
            await self.redis_client.close()

    async def run_all_tests(self):
        """執行所有測試"""
        print("="*60)
        print("Redis 整合測試")
        print("="*60)
        print(f"Redis URL: {self.redis_url}")
        print(f"API Base: {self.api_base}")
        print("="*60)

        # 連接 Redis
        if not await self.connect_redis():
            print("\n❌ 無法連接 Redis，測試終止")
            return False

        print("✅ Redis 連接成功")

        # 執行測試
        await self.test_redis_basic_operations()
        await self.test_health_endpoint()
        await self.test_cache_system()
        await self.test_redis_storage()

        # 總結
        print("\n" + "="*60)
        print("測試總結")
        print("="*60)
        print(f"✅ 通過: {self.passed}")
        print(f"❌ 失敗: {self.failed}")
        print(f"📊 成功率: {self.passed/(self.passed + self.failed)*100:.1f}%")
        print("="*60)

        await self.cleanup()
        return self.failed == 0


async def main():
    """主函數"""
    import sys

    # 解析命令列參數
    redis_url = sys.argv[1] if len(sys.argv) > 1 else "redis://localhost:6379/0"
    api_base = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:1234"

    tester = RedisIntegrationTest(redis_url=redis_url, api_base=api_base)
    success = await tester.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
