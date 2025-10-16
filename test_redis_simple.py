#!/usr/bin/env python3
"""
簡單的 Redis 功能測試
"""
import asyncio
import time
import httpx


async def test_redis_basic():
    """測試基本 Redis 功能"""
    print("="*60)
    print("Redis 簡單功能測試")
    print("="*60)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 測試健康檢查
        print("\n1. 測試健康檢查...")
        response = await client.get("http://localhost:1234/api/health")
        health = response.json()
        print(f"   狀態: {health['status']}")
        print(f"   運行時間: {health['uptime']}s")
        print(f"   活躍郵箱: {health['active_emails']}")

        # 測試生成郵箱
        print("\n2. 測試生成郵箱...")
        response = await client.post("http://localhost:1234/api/email/generate")
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                email_data = data.get("data", {})
                token = email_data.get("token")
                address = email_data.get("address")
                print(f"   ✅ 成功生成: {address}")
                print(f"   Token: {token}")

                # 測試獲取郵件 (多次請求測試快取)
                print("\n3. 測試郵件獲取 (測試快取)...")
                for i in range(3):
                    start = time.time()
                    response = await client.get(f"http://localhost:1234/api/email/{token}/mails?limit=10")
                    duration = (time.time() - start) * 1000

                    if response.status_code == 200:
                        data = response.json()
                        mail_count = len(data.get("data", []))
                        print(f"   請求 {i+1}: {mail_count} 封郵件, 耗時 {duration:.2f}ms")
                    else:
                        print(f"   請求 {i+1}: 失敗 (HTTP {response.status_code})")

                    await asyncio.sleep(0.5)

                # 測試併發請求
                print("\n4. 測試併發請求 (10 個同時請求)...")
                start = time.time()
                tasks = [
                    client.get(f"http://localhost:1234/api/email/{token}/mails?limit=10")
                    for _ in range(10)
                ]
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                duration = (time.time() - start) * 1000

                success = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)
                print(f"   成功: {success}/10")
                print(f"   總耗時: {duration:.2f}ms")
                print(f"   平均: {duration/10:.2f}ms")

            else:
                print(f"   ❌ API 返回失敗: {data.get('message')}")
        else:
            print(f"   ❌ HTTP 錯誤: {response.status_code}")

    print("\n" + "="*60)
    print("測試完成")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(test_redis_basic())
