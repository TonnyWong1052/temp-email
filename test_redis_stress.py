#!/usr/bin/env python3
"""
Redis 壓力測試腳本
測試高併發下的 Redis 性能和快取效果
"""
import asyncio
import time
from datetime import datetime
from typing import List, Dict
import statistics

import httpx


class RedisStressTest:
    """Redis 壓力測試"""

    def __init__(self, api_base: str = "http://localhost:1234", num_workers: int = 50):
        self.api_base = api_base
        self.num_workers = num_workers
        self.results: List[Dict] = []
        self.errors: List[str] = []

    async def generate_email(self, client: httpx.AsyncClient) -> Dict:
        """生成臨時郵箱"""
        try:
            start = time.time()
            response = await client.post(f"{self.api_base}/api/email/generate")
            duration = time.time() - start

            if response.status_code == 200:
                data = response.json()["data"]
                return {
                    "success": True,
                    "token": data["token"],
                    "address": data["address"],
                    "duration": duration
                }
            else:
                return {"success": False, "error": f"HTTP {response.status_code}", "duration": duration}

        except Exception as e:
            return {"success": False, "error": str(e), "duration": 0}

    async def fetch_mails(self, client: httpx.AsyncClient, token: str, use_cache: bool = False) -> Dict:
        """獲取郵件列表"""
        try:
            # 如果要測試快取，先請求一次
            if use_cache:
                await client.get(f"{self.api_base}/api/email/{token}/mails?limit=50")
                await asyncio.sleep(0.5)  # 等待快取建立

            start = time.time()
            response = await client.get(f"{self.api_base}/api/email/{token}/mails?limit=50")
            duration = time.time() - start

            if response.status_code == 200:
                data = response.json()
                mail_count = len(data.get("data", []))
                return {
                    "success": True,
                    "mail_count": mail_count,
                    "duration": duration,
                    "from_cache": use_cache
                }
            else:
                return {"success": False, "error": f"HTTP {response.status_code}", "duration": duration}

        except Exception as e:
            return {"success": False, "error": str(e), "duration": 0}

    async def worker_generate_emails(self, worker_id: int, num_requests: int) -> Dict:
        """工作執行緒：生成郵箱"""
        results = {
            "worker_id": worker_id,
            "total": num_requests,
            "success": 0,
            "failed": 0,
            "durations": [],
            "errors": []
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            for i in range(num_requests):
                result = await self.generate_email(client)

                if result["success"]:
                    results["success"] += 1
                    results["durations"].append(result["duration"])
                else:
                    results["failed"] += 1
                    results["errors"].append(result.get("error", "Unknown"))

        return results

    async def worker_fetch_mails(self, worker_id: int, tokens: List[str], use_cache: bool = False) -> Dict:
        """工作執行緒：獲取郵件"""
        results = {
            "worker_id": worker_id,
            "total": len(tokens),
            "success": 0,
            "failed": 0,
            "durations": [],
            "errors": [],
            "from_cache": use_cache
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            for token in tokens:
                result = await self.fetch_mails(client, token, use_cache)

                if result["success"]:
                    results["success"] += 1
                    results["durations"].append(result["duration"])
                else:
                    results["failed"] += 1
                    results["errors"].append(result.get("error", "Unknown"))

        return results

    async def test_concurrent_email_generation(self, requests_per_worker: int = 20):
        """測試 1: 併發生成郵箱"""
        print("\n" + "="*80)
        print(f"測試 1: 併發生成郵箱 ({self.num_workers} 工作執行緒 x {requests_per_worker} 請求)")
        print("="*80)

        start_time = time.time()

        # 啟動所有工作執行緒
        tasks = [
            self.worker_generate_emails(i, requests_per_worker)
            for i in range(self.num_workers)
        ]

        results = await asyncio.gather(*tasks)
        total_duration = time.time() - start_time

        # 統計結果
        total_success = sum(r["success"] for r in results)
        total_failed = sum(r["failed"] for r in results)
        all_durations = []
        for r in results:
            all_durations.extend(r["durations"])

        # 計算統計數據
        if all_durations:
            avg_duration = statistics.mean(all_durations)
            median_duration = statistics.median(all_durations)
            min_duration = min(all_durations)
            max_duration = max(all_durations)
            p95_duration = sorted(all_durations)[int(len(all_durations) * 0.95)]
            p99_duration = sorted(all_durations)[int(len(all_durations) * 0.99)]
        else:
            avg_duration = median_duration = min_duration = max_duration = p95_duration = p99_duration = 0

        rps = total_success / total_duration if total_duration > 0 else 0

        # 顯示結果
        print(f"\n📊 測試結果:")
        print(f"   總請求數: {total_success + total_failed}")
        print(f"   成功: {total_success}")
        print(f"   失敗: {total_failed}")
        print(f"   成功率: {total_success/(total_success + total_failed)*100:.1f}%")
        print(f"   總耗時: {total_duration:.2f}s")
        print(f"   RPS (每秒請求數): {rps:.2f}")
        print(f"\n⏱️  回應時間統計:")
        print(f"   平均值: {avg_duration*1000:.2f}ms")
        print(f"   中位數: {median_duration*1000:.2f}ms")
        print(f"   最小值: {min_duration*1000:.2f}ms")
        print(f"   最大值: {max_duration*1000:.2f}ms")
        print(f"   P95: {p95_duration*1000:.2f}ms")
        print(f"   P99: {p99_duration*1000:.2f}ms")

        # 收集所有成功的 token
        tokens = []
        for r in results:
            # 這裡需要修改 worker 函數來返回 tokens
            pass

        return {
            "success": total_success,
            "failed": total_failed,
            "rps": rps,
            "avg_duration": avg_duration,
            "p95_duration": p95_duration
        }

    async def test_cache_performance(self):
        """測試 2: 快取性能對比"""
        print("\n" + "="*80)
        print("測試 2: 快取性能對比 (冷快取 vs 熱快取)")
        print("="*80)

        # 先生成一個郵箱
        async with httpx.AsyncClient(timeout=30.0) as client:
            print("\n📧 生成測試郵箱...")
            result = await self.generate_email(client)
            if not result["success"]:
                print("❌ 無法生成測試郵箱")
                return

            token = result["token"]
            print(f"✅ 測試郵箱: {result['address']}")

            # 測試冷快取 (第一次請求)
            print("\n❄️  測試 1: 冷快取 (第一次請求)")
            cold_durations = []
            for i in range(10):
                start = time.time()
                response = await client.get(f"{self.api_base}/api/email/{token}/mails?limit=50")
                duration = time.time() - start
                cold_durations.append(duration)
                await asyncio.sleep(0.1)

            cold_avg = statistics.mean(cold_durations)
            print(f"   平均回應時間: {cold_avg*1000:.2f}ms")
            print(f"   最小值: {min(cold_durations)*1000:.2f}ms")
            print(f"   最大值: {max(cold_durations)*1000:.2f}ms")

            # 測試熱快取 (後續請求)
            print("\n🔥 測試 2: 熱快取 (後續請求)")
            await asyncio.sleep(1)  # 等待快取穩定
            hot_durations = []
            for i in range(10):
                start = time.time()
                response = await client.get(f"{self.api_base}/api/email/{token}/mails?limit=50")
                duration = time.time() - start
                hot_durations.append(duration)
                await asyncio.sleep(0.1)

            hot_avg = statistics.mean(hot_durations)
            print(f"   平均回應時間: {hot_avg*1000:.2f}ms")
            print(f"   最小值: {min(hot_durations)*1000:.2f}ms")
            print(f"   最大值: {max(hot_durations)*1000:.2f}ms")

            # 計算加速比
            speedup = cold_avg / hot_avg if hot_avg > 0 else 0
            improvement = ((cold_avg - hot_avg) / cold_avg * 100) if cold_avg > 0 else 0

            print(f"\n📊 快取效果:")
            print(f"   加速比: {speedup:.2f}x")
            print(f"   性能提升: {improvement:.1f}%")

            if speedup > 1.5:
                print("   ✅ 快取效果顯著")
            elif speedup > 1.1:
                print("   ⚠️  快取效果一般")
            else:
                print("   ❌ 快取可能未生效")

        return {
            "cold_avg": cold_avg,
            "hot_avg": hot_avg,
            "speedup": speedup,
            "improvement": improvement
        }

    async def test_concurrent_reads(self, num_emails: int = 10, concurrent_per_email: int = 10):
        """測試 3: 併發讀取 (測試請求合併)"""
        print("\n" + "="*80)
        print(f"測試 3: 併發讀取 ({num_emails} 個郵箱 x {concurrent_per_email} 併發請求)")
        print("="*80)

        # 生成測試郵箱
        print(f"\n📧 生成 {num_emails} 個測試郵箱...")
        tokens = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for i in range(num_emails):
                result = await self.generate_email(client)
                if result["success"]:
                    tokens.append(result["token"])

        print(f"✅ 已生成 {len(tokens)} 個測試郵箱")

        # 對每個郵箱發起併發請求
        print(f"\n🚀 對每個郵箱發起 {concurrent_per_email} 個併發請求...")
        start_time = time.time()
        async with httpx.AsyncClient(timeout=30.0) as client:
            all_tasks = []
            for token in tokens:
                for _ in range(concurrent_per_email):
                    task = self.fetch_mails(client, token, use_cache=False)
                    all_tasks.append(task)
            # 確保在關閉 client 之前等待所有請求完成
            results = await asyncio.gather(*all_tasks, return_exceptions=True)
        total_duration = time.time() - start_time

        # 統計結果
        # 忽略異常，僅統計成功/失敗
        normalized = [r for r in results if isinstance(r, dict)]
        success_count = sum(1 for r in normalized if r.get("success"))
        failed_count = sum(1 for r in normalized if not r.get("success"))
        durations = [r["duration"] for r in normalized if r.get("success")]

        if durations:
            avg_duration = statistics.mean(durations)
            p95_duration = sorted(durations)[int(len(durations) * 0.95)]
        else:
            avg_duration = p95_duration = 0

        rps = success_count / total_duration if total_duration > 0 else 0

        print(f"\n📊 測試結果:")
        print(f"   總請求數: {len(results)}")
        print(f"   成功: {success_count}")
        print(f"   失敗: {failed_count}")
        print(f"   成功率: {success_count/len(results)*100:.1f}%")
        print(f"   總耗時: {total_duration:.2f}s")
        print(f"   RPS: {rps:.2f}")
        print(f"   平均回應時間: {avg_duration*1000:.2f}ms")
        print(f"   P95 回應時間: {p95_duration*1000:.2f}ms")

        return {
            "success": success_count,
            "failed": failed_count,
            "rps": rps,
            "avg_duration": avg_duration,
            "p95_duration": p95_duration
        }

    async def run_all_tests(self):
        """執行所有測試"""
        print("="*80)
        print("Redis 壓力測試")
        print("="*80)
        print(f"API Base: {self.api_base}")
        print(f"工作執行緒數: {self.num_workers}")
        print(f"開始時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)

        # 測試 1: 併發生成郵箱
        test1_result = await self.test_concurrent_email_generation(requests_per_worker=20)

        # 測試 2: 快取性能對比
        test2_result = await self.test_cache_performance()

        # 測試 3: 併發讀取
        test3_result = await self.test_concurrent_reads(num_emails=10, concurrent_per_email=10)

        # 總結
        print("\n" + "="*80)
        print("測試總結")
        print("="*80)
        print(f"\n📧 測試 1 - 併發生成郵箱:")
        print(f"   成功率: {test1_result['success']/(test1_result['success'] + test1_result['failed'])*100:.1f}%")
        print(f"   RPS: {test1_result['rps']:.2f}")
        print(f"   平均回應時間: {test1_result['avg_duration']*1000:.2f}ms")

        print(f"\n🔥 測試 2 - 快取性能:")
        print(f"   加速比: {test2_result['speedup']:.2f}x")
        print(f"   性能提升: {test2_result['improvement']:.1f}%")

        print(f"\n🚀 測試 3 - 併發讀取:")
        print(f"   成功率: {test3_result['success']/(test3_result['success'] + test3_result['failed'])*100:.1f}%")
        print(f"   RPS: {test3_result['rps']:.2f}")
        print(f"   P95 回應時間: {test3_result['p95_duration']*1000:.2f}ms")

        print("\n" + "="*80)
        print(f"結束時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)


async def main():
    """主函數"""
    import sys

    api_base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:1234"
    num_workers = int(sys.argv[2]) if len(sys.argv) > 2 else 50

    tester = RedisStressTest(api_base=api_base, num_workers=num_workers)
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
