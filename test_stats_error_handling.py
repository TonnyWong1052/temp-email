#!/usr/bin/env python3
"""
測試統計 API 的錯誤處理機制
模擬各種錯誤情況並驗證錯誤日誌記錄
"""

import requests
import json
import sys

# 配置
BASE_URL = "http://127.0.0.1:1234"
USERNAME = "tomleung"
PASSWORD = "tomleung"


def login():
    """登錄並獲取 token"""
    response = requests.post(
        f"{BASE_URL}/admin/login",
        json={"username": USERNAME, "password": PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("token")
    else:
        print(f"❌ 登錄失敗: {response.status_code}")
        print(response.text)
        sys.exit(1)


def test_normal_stats(token):
    """測試正常的統計 API"""
    print("\n" + "="*60)
    print("測試 1: 正常統計 API 調用")
    print("="*60)

    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/admin/logs/stats", headers=headers)

    print(f"HTTP Status: {response.status_code}")
    print(f"Response:")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))

    if response.status_code == 200 and response.json().get("success"):
        print("✅ 測試通過：正常統計 API 工作正常")
    else:
        print("❌ 測試失敗：正常統計 API 返回錯誤")


def test_invalid_token():
    """測試無效 token（認證錯誤）"""
    print("\n" + "="*60)
    print("測試 2: 無效 Token（預期 401 錯誤）")
    print("="*60)

    headers = {"Authorization": "Bearer invalid_token_123"}
    response = requests.get(f"{BASE_URL}/admin/logs/stats", headers=headers)

    print(f"HTTP Status: {response.status_code}")
    print(f"Response:")
    try:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    except:
        print(response.text[:500])

    if response.status_code == 401:
        print("✅ 測試通過：正確返回 401 認證錯誤")
    else:
        print(f"❌ 測試失敗：預期 401，實際 {response.status_code}")


def test_missing_auth():
    """測試缺少認證（認證錯誤）"""
    print("\n" + "="*60)
    print("測試 3: 缺少認證頭（預期 401 錯誤）")
    print("="*60)

    response = requests.get(f"{BASE_URL}/admin/logs/stats")

    print(f"HTTP Status: {response.status_code}")
    print(f"Response:")
    try:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    except:
        print(response.text[:500])

    if response.status_code == 401:
        print("✅ 測試通過：正確返回 401 認證錯誤")
    else:
        print(f"❌ 測試失敗：預期 401，實際 {response.status_code}")


def test_high_load_stats(token):
    """測試高負載情況（生成大量日誌後統計）"""
    print("\n" + "="*60)
    print("測試 4: 高負載統計（生成 50 個郵箱後統計）")
    print("="*60)

    # 生成 50 個臨時郵箱，增加日誌數量
    print("生成測試數據...")
    for i in range(50):
        try:
            requests.post(f"{BASE_URL}/api/email/generate", timeout=2)
        except:
            pass

    # 調用統計 API
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/admin/logs/stats", headers=headers)

    print(f"HTTP Status: {response.status_code}")
    data = response.json()

    if response.status_code == 200 and data.get("success"):
        total = data.get("stats", {}).get("total", 0)
        print(f"✅ 測試通過：成功統計 {total} 條日誌")
        print(f"詳細統計:")
        print(json.dumps(data.get("stats"), indent=2, ensure_ascii=False))
    else:
        print("❌ 測試失敗：高負載統計失敗")
        print(json.dumps(data, indent=2, ensure_ascii=False))


def check_log_files():
    """檢查錯誤是否被記錄到日誌文件"""
    print("\n" + "="*60)
    print("檢查日誌文件中的錯誤記錄")
    print("="*60)

    import os
    from pathlib import Path

    log_dir = Path("logs")
    if not log_dir.exists():
        print("⚠️ 日誌目錄不存在，跳過日誌文件檢查")
        return

    # 查找最新的錯誤日誌
    error_log = log_dir / "error.log"
    app_log = log_dir / "app.log"

    print("\n檢查 error.log:")
    if error_log.exists():
        with open(error_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if lines:
                print(f"  - 找到 {len(lines)} 行錯誤日誌")
                print(f"  - 最近 5 條:")
                for line in lines[-5:]:
                    print(f"    {line.strip()}")
            else:
                print("  - 錯誤日誌為空")
    else:
        print("  - error.log 不存在")

    print("\n檢查 app.log:")
    if app_log.exists():
        with open(app_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            error_lines = [l for l in lines if '[ERROR]' in l or 'ERROR' in l]
            print(f"  - 總日誌行數: {len(lines)}")
            print(f"  - 錯誤日誌行數: {len(error_lines)}")
            if error_lines:
                print(f"  - 最近 3 條錯誤:")
                for line in error_lines[-3:]:
                    print(f"    {line.strip()}")
    else:
        print("  - app.log 不存在")


def main():
    print("🧪 統計 API 錯誤處理測試")
    print("="*60)

    # 登錄
    print("\n登錄中...")
    token = login()
    print(f"✅ 登錄成功，Token: {token[:30]}...")

    # 運行測試
    test_normal_stats(token)
    test_invalid_token()
    test_missing_auth()
    test_high_load_stats(token)
    check_log_files()

    print("\n" + "="*60)
    print("✅ 所有測試完成")
    print("="*60)


if __name__ == "__main__":
    main()
