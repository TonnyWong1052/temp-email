"""
Cloudflare 配置辅助服务

提供三种方式帮助用户配置 Cloudflare Workers KV:
1. 配置向导 (Step-by-Step Guide)
2. 连接测试 (Connection Validator)
3. Wrangler CLI 自动检测 (Auto-Detection)
"""

import asyncio
import json
import subprocess
from typing import Dict, Any, List, Optional, Tuple
import httpx

from app.services.log_service import log_service, LogLevel, LogType


class CloudflareHelper:
    """Cloudflare 配置辅助工具"""

    @staticmethod
    def get_wizard_steps() -> List[Dict[str, Any]]:
        """
        获取配置向导步骤（包含 Worker 部署）

        Returns:
            向导步骤列表
        """
        return [
            {
                "id": 1,
                "title": "获取 Cloudflare 账户 ID",
                "description": "1. 登录 Cloudflare Dashboard\n2. 在右侧边栏找到三个点按钮 (⋮) 并点击\n3. 在下拉菜单中找到并复制帐户 ID",
                "url": "https://dash.cloudflare.com/",
                "hint": "帐户 ID 是一串 32 位十六进制字符串，类似: 1234567890abcdef1234567890abcdef",
                "field_id": "cfAccountId",
                "icon": "🆔"
            },
            {
                "id": 2,
                "title": "创建 API Token",
                "description": "点击「Create Token」，选择「Custom Token」，设置以下权限：\n\n🔑 必需权限：\n• Account Settings: Read - 读取帐户信息\n• Workers KV Storage: Read - 读取 KV 数据\n\n🔍 域名检查功能（可选）：\n• Zone: Read - 读取域名列表\n• Email Routing Rules: Read - 读取 Email Routing 配置\n\n添加这些权限后，系统将能够自动检测您的域名并验证 Email Routing 配置状态。",
                "url": "https://dash.cloudflare.com/profile/api-tokens",
                "hint": "复制生成的 Token 到下方「API Token」栏位（只显示一次，请妥善保存）",
                "field_id": "cfApiToken",
                "icon": "🔑"
            },
            {
                "id": 3,
                "title": "创建 KV Namespace",
                "description": "进入 Workers & Pages → KV，点击「Create namespace」按钮，输入名称（如 EMAIL_STORAGE）",
                "url": "https://dash.cloudflare.com/?to=/:account/workers/kv/namespaces",
                "hint": "创建完成后，复制 Namespace ID 到下方栏位",
                "field_id": "cfKvNamespaceId",
                "icon": "📦"
            },
            {
                "id": 4,
                "title": "检查部署环境",
                "description": "确保已安装 Node.js (v18+) 和 npm:\n\n• 检查命令: node -v && npm -v\n• 如未安装，请访问 nodejs.org 下载",
                "hint": "部署脚本需要 Node.js 环境来运行 Wrangler CLI",
                "field_id": None,
                "icon": "🔧",
                "command": "node -v && npm -v"
            },
            {
                "id": 5,
                "title": "运行部署cloudflare worker脚本",
                "description": "如果尚未安装项目，请先克隆仓库:\ngit clone https://github.com/TonnyWong1052/temp-email.git\ncd temp-email\n\n然后在项目根目录执行部署脚本:\ncd workers\n./deploy.sh\n\n脚本会自动完成:\n1. 安装/检查 Wrangler CLI\n2. 登录 Cloudflare（首次需要浏览器授权）\n3. 创建 KV Namespace\n4. 部署 Email Worker 到 Cloudflare\n5. 生成 wrangler.toml 配置文件\n\n💡 手动配置 Wrangler（可选）：\n• 如需手动配置，可使用本页的「🧩 Wrangler 片段」或「✍️ 写入 wrangler.toml」功能\n• 生成 wrangler.toml 配置片段，复制到 workers/wrangler.toml 文件中\n• 然后运行: wrangler deploy",
                "url": "https://github.com/TonnyWong1052/temp-email",
                "hint": "首次运行会打开浏览器进行 Cloudflare 授权，请确保已登录 Cloudflare 账户。部署完成后会自动生成 wrangler.toml 配置。",
                "field_id": None,
                "icon": "🚀"
            },
            {
                "id": 6,
                "title": "配置 Email Routing",
                "description": "在 Cloudflare Dashboard 中设置邮件路由:\n\n1. 选择您的域名\n2. 进入 Email → Email Routing\n3. 点击「启用电子邮件路由」(Enable Email Routing)\n4. 启用后，点击「路由规则」(Routing rules) 选项卡\n5. 找到 Catch-All 规则，点击「编辑」(Edit)\n6. 在「操作」下拉菜单中选择「发送到 Worker」\n7. 选择 Worker: temp-email-worker\n8. 点击保存",
                "url": "https://dash.cloudflare.com/?to=/:account/:zone/email/routing/routes",
                "hint": "Catch-All 规则会将所有发送到该域名的邮件转发给 Worker 处理",
                "field_id": None,
                "icon": "📧"
            }
        ]

    @staticmethod
    async def test_connection(
        account_id: str,
        namespace_id: str,
        api_token: str
    ) -> Dict[str, Any]:
        """
        测试 Cloudflare KV 连接

        执行三层验证：
        1. API Token 权限检查
        2. Account ID 验证
        3. Namespace ID 访问测试

        Args:
            account_id: Cloudflare 账户 ID
            namespace_id: KV Namespace ID
            api_token: Cloudflare API Token

        Returns:
            测试结果字典
        """
        checks = []
        overall_status = "success"

        try:
            # 检查 1: 验证 API Token
            token_check = await CloudflareHelper._verify_token(api_token)
            checks.append(token_check)

            if token_check["status"] != "passed":
                overall_status = "failed"
                return {
                    "success": False,
                    "checks": checks,
                    "overall_status": overall_status,
                    "message": "API Token 验证失败，请检查 Token 是否正确"
                }

            # 检查 2: 验证 Account ID（尝试列出 KV Namespaces）
            account_check = await CloudflareHelper._verify_account(account_id, api_token)
            checks.append(account_check)

            if account_check["status"] != "passed":
                overall_status = "failed"
                return {
                    "success": False,
                    "checks": checks,
                    "overall_status": overall_status,
                    "message": "Account ID 验证失败，请检查 ID 是否正确"
                }

            # 检查 3: 验证 Namespace ID（尝试读取 KV keys）
            namespace_check = await CloudflareHelper._verify_namespace(
                account_id, namespace_id, api_token
            )
            checks.append(namespace_check)

            if namespace_check["status"] != "passed":
                overall_status = "failed"
                return {
                    "success": False,
                    "checks": checks,
                    "overall_status": overall_status,
                    "message": "Namespace ID 验证失败，请检查 ID 是否正确或 Token 权限是否足够"
                }

            # 所有检查通过
            await log_service.log(
                level=LogLevel.SUCCESS,
                log_type=LogType.SYSTEM,
                message="Cloudflare KV 连接测试成功",
                details={
                    "account_id": account_id[:8] + "...",
                    "namespace_id": namespace_id[:8] + "..."
                }
            )

            return {
                "success": True,
                "checks": checks,
                "overall_status": "success",
                "message": "所有检查通过！✅ Cloudflare KV 配置正确"
            }

        except Exception as e:
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.SYSTEM,
                message=f"Cloudflare 连接测试异常: {str(e)}",
                details={
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )

            return {
                "success": False,
                "checks": checks,
                "overall_status": "error",
                "message": f"测试过程中发生错误: {str(e)}"
            }

    @staticmethod
    async def _verify_token(api_token: str) -> Dict[str, Any]:
        """验证 API Token 是否有效"""
        try:
            url = "https://api.cloudflare.com/client/v4/user/tokens/verify"
            headers = {"Authorization": f"Bearer {api_token}"}

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        return {
                            "name": "API Token 验证",
                            "status": "passed",
                            "message": "Token 有效且可用",
                            "icon": "✅"
                        }

                return {
                    "name": "API Token 验证",
                    "status": "failed",
                    "message": f"Token 无效或权限不足 (HTTP {response.status_code})",
                    "icon": "❌"
                }

        except Exception as e:
            return {
                "name": "API Token 验证",
                "status": "failed",
                "message": f"验证失败: {str(e)}",
                "icon": "❌"
            }

    @staticmethod
    async def _get_token_accounts(api_token: str) -> List[str]:
        """
        获取 Token 有权访问的所有 Account ID

        Args:
            api_token: Cloudflare API Token

        Returns:
            Account ID 列表（如果失败返回空列表）
        """
        try:
            url = "https://api.cloudflare.com/client/v4/accounts"
            headers = {"Authorization": f"Bearer {api_token}"}

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers, params={"per_page": 50})

                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        accounts = data.get("result", [])
                        return [acc.get("id") for acc in accounts if acc.get("id")]

            return []

        except Exception as e:
            await log_service.log(
                level=LogLevel.WARNING,
                log_type=LogType.SYSTEM,
                message=f"获取 Token Accounts 失败: {str(e)}",
                details={"error": str(e)}
            )
            return []

    @staticmethod
    async def _get_namespace_account(namespace_id: str, api_token: str) -> Optional[str]:
        """
        获取 Namespace 实际所属的 Account ID（通过搜索所有可访问的 Accounts）

        Args:
            namespace_id: KV Namespace ID
            api_token: Cloudflare API Token

        Returns:
            Account ID（如果找到），否则返回 None
        """
        try:
            # 先获取所有可访问的 Accounts
            token_accounts = await CloudflareHelper._get_token_accounts(api_token)

            if not token_accounts:
                return None

            # 在每个 Account 中搜索此 Namespace
            for account_id in token_accounts:
                try:
                    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces"
                    headers = {"Authorization": f"Bearer {api_token}"}

                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.get(url, headers=headers, params={"per_page": 100})

                        if response.status_code == 200:
                            data = response.json()
                            if data.get("success"):
                                namespaces = data.get("result", [])
                                # 检查是否包含目标 Namespace
                                for ns in namespaces:
                                    if ns.get("id") == namespace_id:
                                        return account_id

                except Exception as e:
                    # 跳过无法访问的 Account
                    continue

            return None

        except Exception as e:
            await log_service.log(
                level=LogLevel.WARNING,
                log_type=LogType.SYSTEM,
                message=f"搜索 Namespace Account 失败: {str(e)}",
                details={"namespace_id": namespace_id, "error": str(e)}
            )
            return None

    @staticmethod
    async def _verify_account(account_id: str, api_token: str) -> Dict[str, Any]:
        """验证 Account ID 是否正确（增强版：检测 Token 可访问的 Accounts）"""
        try:
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces"
            headers = {"Authorization": f"Bearer {api_token}"}

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers, params={"per_page": 1})

                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        return {
                            "name": "Account ID 验证",
                            "status": "passed",
                            "message": "Account ID 正确",
                            "icon": "✅",
                            "details": {
                                "account_id": account_id,
                                "accessible": True
                            }
                        }
                elif response.status_code == 403:
                    return {
                        "name": "Account ID 验证",
                        "status": "failed",
                        "message": "权限不足，请检查 API Token 是否有 'Account Settings: Read' 权限",
                        "icon": "❌"
                    }
                elif response.status_code == 404:
                    # ⭐ 增强：检查 Token 实际能访问哪些 Accounts
                    token_accounts = await CloudflareHelper._get_token_accounts(api_token)

                    if token_accounts:
                        accounts_preview = ", ".join([acc[:8] + "..." for acc in token_accounts[:3]])
                        count_msg = f"（共 {len(token_accounts)} 个）" if len(token_accounts) > 3 else ""

                        return {
                            "name": "Account ID 验证",
                            "status": "failed",
                            "message": f"Token 无法访问此 Account ID。Token 实际可访问: {accounts_preview} {count_msg}",
                            "icon": "❌",
                            "details": {
                                "requested_account": account_id,
                                "accessible_accounts": token_accounts,
                                "mismatch": True
                            }
                        }
                    else:
                        return {
                            "name": "Account ID 验证",
                            "status": "failed",
                            "message": "Account ID 不存在或 Token 无法访问任何 Account",
                            "icon": "❌"
                        }

                return {
                    "name": "Account ID 验证",
                    "status": "failed",
                    "message": f"验证失败 (HTTP {response.status_code})",
                    "icon": "❌"
                }

        except Exception as e:
            return {
                "name": "Account ID 验证",
                "status": "failed",
                "message": f"验证失败: {str(e)}",
                "icon": "❌"
            }

    @staticmethod
    async def _verify_namespace(
        account_id: str,
        namespace_id: str,
        api_token: str
    ) -> Dict[str, Any]:
        """验证 Namespace ID 是否可访问"""
        try:
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/keys"
            headers = {"Authorization": f"Bearer {api_token}"}

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers, params={"limit": 10})

                # 记录详细的响应信息用于调试
                await log_service.log(
                    level=LogLevel.INFO,
                    log_type=LogType.SYSTEM,
                    message=f"KV Namespace 访问测试: HTTP {response.status_code}",
                    details={
                        "url": url,
                        "status_code": response.status_code,
                        "response_body": response.text[:500] if response.text else None
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        key_count = len(data.get("result", []))
                        return {
                            "name": "KV Namespace 访问",
                            "status": "passed",
                            "message": f"成功连接到 Namespace (当前有 {key_count}+ keys)",
                            "icon": "✅"
                        }
                elif response.status_code == 400:
                    # HTTP 400: Bad Request - 通常是请求参数错误
                    try:
                        error_data = response.json()
                        errors = error_data.get("errors", [])
                        error_msg = errors[0].get("message", "未知错误") if errors else "请求格式错误"
                        return {
                            "name": "KV Namespace 访问",
                            "status": "failed",
                            "message": f"请求参数错误: {error_msg}",
                            "icon": "❌"
                        }
                    except:
                        return {
                            "name": "KV Namespace 访问",
                            "status": "failed",
                            "message": "请求参数错误 (HTTP 400)，请检查 Account ID 和 Namespace ID 格式",
                            "icon": "❌"
                        }
                elif response.status_code == 403:
                    return {
                        "name": "KV Namespace 访问",
                        "status": "failed",
                        "message": "权限不足，请检查 API Token 是否有 'Workers KV Storage: Read' 权限",
                        "icon": "❌"
                    }
                elif response.status_code == 404:
                    # ⭐ 增强：检查 Namespace 实际属于哪个 Account
                    actual_account = await CloudflareHelper._get_namespace_account(namespace_id, api_token)

                    if actual_account and actual_account != account_id:
                        return {
                            "name": "KV Namespace 访问",
                            "status": "failed",
                            "message": f"Namespace 属于 Account {actual_account[:8]}..., 而非当前配置的 {account_id[:8]}...",
                            "icon": "❌",
                            "details": {
                                "requested_account": account_id,
                                "actual_account": actual_account,
                                "namespace_id": namespace_id,
                                "mismatch": True
                            }
                        }
                    else:
                        return {
                            "name": "KV Namespace 访问",
                            "status": "failed",
                            "message": "Namespace ID 不存在或无法访问",
                            "icon": "❌"
                        }

                # 其他错误返回详细信息
                try:
                    error_data = response.json()
                    errors = error_data.get("errors", [])
                    error_msg = errors[0].get("message", "") if errors else response.text[:100]
                except:
                    error_msg = response.text[:100] if response.text else "未知错误"

                return {
                    "name": "KV Namespace 访问",
                    "status": "failed",
                    "message": f"访问失败 (HTTP {response.status_code}): {error_msg}",
                    "icon": "❌"
                }

        except Exception as e:
            return {
                "name": "KV Namespace 访问",
                "status": "failed",
                "message": f"访问失败: {str(e)}",
                "icon": "❌"
            }

    @staticmethod
    async def verify_config_match(
        account_id: str,
        namespace_id: str,
        api_token: str
    ) -> Dict[str, Any]:
        """
        综合验证三个配置项是否相互匹配

        执行检查：
        1. Token 是否能访问指定的 Account
        2. Namespace 是否属于指定的 Account
        3. Token 是否有权限访问此 Namespace

        Args:
            account_id: Cloudflare 账户 ID
            namespace_id: KV Namespace ID
            api_token: Cloudflare API Token

        Returns:
            {
                "match": bool,  # 是否完全匹配
                "token_accounts": List[str],  # Token 能访问的 Account 列表
                "namespace_account": Optional[str],  # Namespace 实际所属的 Account
                "issues": List[str],  # 不匹配的问题列表
                "suggestions": List[str]  # 修复建议
            }
        """
        result = {
            "match": True,
            "token_accounts": [],
            "namespace_account": None,
            "issues": [],
            "suggestions": []
        }

        try:
            # 获取 Token 可访问的 Accounts
            token_accounts = await CloudflareHelper._get_token_accounts(api_token)
            result["token_accounts"] = token_accounts

            # 检查 Token 是否能访问指定的 Account
            if token_accounts and account_id not in token_accounts:
                result["match"] = False
                result["issues"].append(
                    f"Token 无法访问 Account {account_id[:8]}..."
                )

                accounts_preview = ", ".join([acc[:8] + "..." for acc in token_accounts[:3]])
                count_suffix = f" (共 {len(token_accounts)} 个)" if len(token_accounts) > 3 else ""

                result["suggestions"].append(
                    f"💡 Token 实际可访问: {accounts_preview}{count_suffix}\n"
                    f"   请确认 Account ID 是否填写正确，或使用 Token 可访问的 Account"
                )

            # 获取 Namespace 实际所属的 Account
            namespace_account = await CloudflareHelper._get_namespace_account(namespace_id, api_token)
            result["namespace_account"] = namespace_account

            if namespace_account:
                # 检查 Namespace 是否属于指定的 Account
                if namespace_account != account_id:
                    result["match"] = False
                    result["issues"].append(
                        f"Namespace {namespace_id[:8]}... 属于 Account {namespace_account[:8]}..., "
                        f"而非当前配置的 {account_id[:8]}..."
                    )
                    result["suggestions"].append(
                        f"💡 请将 Account ID 修改为 {namespace_account}，或选择属于 {account_id[:8]}... 的其他 Namespace"
                    )

            # 如果完全匹配
            if result["match"]:
                result["suggestions"].append(
                    "✅ 所有配置项相互匹配，Cloudflare KV 已准备就绪！"
                )

            return result

        except Exception as e:
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.SYSTEM,
                message=f"配置匹配度检查异常: {str(e)}",
                details={
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )

            result["match"] = False
            result["issues"].append(f"匹配度检查失败: {str(e)}")
            return result

    @staticmethod
    async def list_account_zones(account_id: str, api_token: str) -> Dict[str, Any]:
        """
        列出 Account 下的所有域名（Zones）

        Args:
            account_id: Cloudflare 账户 ID
            api_token: Cloudflare API Token

        Returns:
            {
                "success": bool,
                "zones": List[Dict],  # 域名列表
                "count": int,  # 域名数量
                "message": str
            }
        """
        try:
            url = "https://api.cloudflare.com/client/v4/zones"
            headers = {"Authorization": f"Bearer {api_token}"}
            params = {
                "account.id": account_id,
                "per_page": 50  # 最多返回 50 个域名
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers, params=params)

                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        zones = data.get("result", [])
                        return {
                            "success": True,
                            "zones": zones,
                            "count": len(zones),
                            "message": f"成功获取 {len(zones)} 个域名"
                        }

                return {
                    "success": False,
                    "zones": [],
                    "count": 0,
                    "message": f"获取域名失败 (HTTP {response.status_code})"
                }

        except Exception as e:
            return {
                "success": False,
                "zones": [],
                "count": 0,
                "message": f"获取域名异常: {str(e)}"
            }

    @staticmethod
    async def check_email_routing_status(zone_id: str, api_token: str) -> Dict[str, Any]:
        """
        检查单个域名的 Email Routing 配置

        Args:
            zone_id: Cloudflare Zone ID
            api_token: Cloudflare API Token

        Returns:
            {
                "enabled": bool,  # Email Routing 是否启用
                "status": str,  # 状态
                "has_catch_all": bool,  # 是否有 Catch-All 规则
                "worker_route": Optional[str]  # Worker 路由名称
            }
        """
        try:
            # 检查 Email Routing 是否启用
            routing_url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/email/routing"
            headers = {"Authorization": f"Bearer {api_token}"}

            async with httpx.AsyncClient(timeout=10.0) as client:
                # 获取 Email Routing 状态
                routing_response = await client.get(routing_url, headers=headers)

                if routing_response.status_code == 200:
                    routing_data = routing_response.json()
                    if routing_data.get("success"):
                        result = routing_data.get("result", {})
                        enabled = result.get("enabled", False)
                        status = result.get("status", "unknown")

                        # 如果启用，检查 Catch-All 规则
                        has_catch_all = False
                        worker_route = None

                        if enabled:
                            rules_url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/email/routing/rules/catch_all"
                            rules_response = await client.get(rules_url, headers=headers)

                            if rules_response.status_code == 200:
                                rules_data = rules_response.json()
                                if rules_data.get("success"):
                                    catch_all = rules_data.get("result", {})
                                    has_catch_all = catch_all.get("enabled", False)

                                    # 检查是否指向 Worker
                                    actions = catch_all.get("actions", [])
                                    for action in actions:
                                        if action.get("type") == "worker":
                                            worker_route = action.get("value", [])[0] if action.get("value") else None

                        return {
                            "enabled": enabled,
                            "status": status,
                            "has_catch_all": has_catch_all,
                            "worker_route": worker_route
                        }

                return {
                    "enabled": False,
                    "status": "unknown",
                    "has_catch_all": False,
                    "worker_route": None
                }

        except Exception as e:
            return {
                "enabled": False,
                "status": "error",
                "has_catch_all": False,
                "worker_route": None,
                "error": str(e)
            }

    @staticmethod
    async def check_domains_with_api(
        account_id: str,
        api_token: str,
        cf_kv_domains: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        综合域名检查（使用 Cloudflare API）

        执行步骤：
        1. 获取所有域名列表
        2. 检查每个域名的 Email Routing 状态
        3. 对比 CF_KV_DOMAINS 配置（如果存在）
        4. 生成配置建议

        Args:
            account_id: Cloudflare 账户 ID
            api_token: Cloudflare API Token
            cf_kv_domains: CF_KV_DOMAINS 配置值（可选）

        Returns:
            {
                "success": bool,
                "cloudflare_zones": List[Dict],  # Cloudflare 实际域名
                "configured_domains": List[str],  # CF_KV_DOMAINS 配置
                "email_routing_status": Dict,  # Email Routing 状态
                "suggestions": List[str],  # 配置建议
                "message": str
            }
        """
        from app.config import parse_domain_list

        result = {
            "success": False,
            "cloudflare_zones": [],
            "configured_domains": [],
            "email_routing_status": {},
            "suggestions": [],
            "message": ""
        }

        try:
            # 步骤 1: 获取 Cloudflare 域名列表
            zones_result = await CloudflareHelper.list_account_zones(account_id, api_token)

            if not zones_result.get("success"):
                # ⚠️ 修复：返回权限错误而不是 "检测到 0 个域名"
                error_msg = zones_result.get('message', '未知错误')
                result["message"] = f"❌ 无法获取 Cloudflare 域名列表"
                result["suggestions"].append(
                    f"🔍 错误原因: {error_msg}"
                )
                result["suggestions"].append(
                    "🔑 请检查 API Token 是否具有以下权限："
                )
                result["suggestions"].append(
                    "   • Zone: Read - 读取域名列表"
                )
                result["suggestions"].append(
                    "   • Email Routing Rules: Read - 读取 Email Routing 配置（可选）"
                )
                result["suggestions"].append(
                    f"🆔 请确认 Account ID ({account_id[:8]}...) 是否正确"
                )
                return result

            zones = zones_result.get("zones", [])
            result["cloudflare_zones"] = [
                {
                    "name": zone.get("name"),
                    "id": zone.get("id"),
                    "status": zone.get("status")
                }
                for zone in zones
            ]

            # 步骤 2: 检查每个域名的 Email Routing 状态
            for zone in zones:
                zone_name = zone.get("name")
                zone_id = zone.get("id")

                routing_status = await CloudflareHelper.check_email_routing_status(zone_id, api_token)
                result["email_routing_status"][zone_name] = routing_status

            # 步骤 3: 解析 CF_KV_DOMAINS 配置
            if cf_kv_domains:
                configured = parse_domain_list(cf_kv_domains)
                result["configured_domains"] = configured

            # 步骤 4: 生成建议
            cloudflare_domain_names = [z.get("name") for z in zones]

            # 检查未启用 Email Routing 的域名
            not_enabled = [
                name for name, status in result["email_routing_status"].items()
                if not status.get("enabled")
            ]

            if not_enabled:
                result["suggestions"].append(
                    f"📧 以下 {len(not_enabled)} 个域名未启用 Email Routing: {', '.join(not_enabled[:3])}"
                )
                result["suggestions"].append(
                    "💡 启用方法: Cloudflare Dashboard → 域名 → Email → Email Routing → 启用"
                )

            # 检查未配置 Catch-All 的域名
            no_catch_all = [
                name for name, status in result["email_routing_status"].items()
                if status.get("enabled") and not status.get("has_catch_all")
            ]

            if no_catch_all:
                result["suggestions"].append(
                    f"⚙️ 以下域名未配置 Catch-All 规则: {', '.join(no_catch_all[:3])}"
                )
                result["suggestions"].append(
                    "🔧 配置方法: Email Routing → Routing rules → Catch-All → 发送到 Worker"
                )

            # 检查已配置 Worker 的域名
            with_worker = [
                name for name, status in result["email_routing_status"].items()
                if status.get("worker_route")
            ]

            # 对比 CF_KV_DOMAINS
            if result["configured_domains"]:
                # 在配置中但不在 Cloudflare
                not_in_cloudflare = [
                    d for d in result["configured_domains"]
                    if d not in cloudflare_domain_names
                ]

                if not_in_cloudflare:
                    result["suggestions"].append(
                        f"⚠️ CF_KV_DOMAINS 中有 {len(not_in_cloudflare)} 个域名不在 Cloudflare 账户中: {', '.join(not_in_cloudflare)}"
                    )

                # 在 Cloudflare 但不在配置中（且已启用 Email Routing）
                enabled_not_configured = [
                    name for name in cloudflare_domain_names
                    if name not in result["configured_domains"]
                    and result["email_routing_status"].get(name, {}).get("enabled")
                ]

                if enabled_not_configured:
                    result["suggestions"].append(
                        f"💡 建议将以下域名添加到 CF_KV_DOMAINS: {', '.join(enabled_not_configured[:3])}"
                    )
                    result["suggestions"].append(
                        f"   推荐配置: {json.dumps(result['configured_domains'] + enabled_not_configured[:3], ensure_ascii=False)}"
                    )
            else:
                # 没有配置 CF_KV_DOMAINS，建议配置
                if with_worker:
                    result["suggestions"].append(
                        f"💡 检测到 {len(with_worker)} 个域名已配置 Worker，建议添加到 CF_KV_DOMAINS:"
                    )
                    result["suggestions"].append(
                        f"   推荐配置: {json.dumps(with_worker, ensure_ascii=False)}"
                    )

            # 成功消息
            enabled_count = len([s for s in result["email_routing_status"].values() if s.get("enabled")])
            result["success"] = True
            result["message"] = f"✅ 检测到 {len(zones)} 个域名，其中 {enabled_count} 个已启用 Email Routing"

            return result

        except Exception as e:
            result["message"] = f"❌ 域名检查异常: {str(e)}"
            result["suggestions"].append("🔧 请检查网络连接和 API 权限")
            return result

    @staticmethod
    def check_domains_config(cf_kv_domains: Optional[str]) -> Dict[str, Any]:
        """
        检查自定义域名配置 (CF_KV_DOMAINS)

        Args:
            cf_kv_domains: CF_KV_DOMAINS 配置值 (JSON 字符串)

        Returns:
            {
                "configured": bool,  # 是否已配置
                "domains": List[str],  # 域名列表
                "count": int,  # 域名数量
                "routing_mode": str,  # 路由模式
                "status": str,  # 状态 (ok, warning, error)
                "message": str,  # 状态消息
                "suggestions": List[str]  # 配置建议
            }
        """
        import json
        from app.config import get_active_domains, parse_domain_list

        result = {
            "configured": False,
            "domains": [],
            "count": 0,
            "routing_mode": "unknown",
            "status": "ok",
            "message": "",
            "suggestions": []
        }

        try:
            # 检查是否已配置 CF_KV_DOMAINS
            if not cf_kv_domains or not cf_kv_domains.strip():
                result["routing_mode"] = "all_kv"
                result["status"] = "warning"
                result["message"] = "⚠️ CF_KV_DOMAINS 未配置，所有域名将使用 Cloudflare KV"
                result["suggestions"].append(
                    "💡 如果您只想让部分域名使用 KV，请配置 CF_KV_DOMAINS（JSON 格式）"
                )
                result["suggestions"].append(
                    "📖 例如: [\"example.com\", \"yourdomain.com\"]"
                )
                return result

            # 解析域名列表
            domains = parse_domain_list(cf_kv_domains)

            if not domains:
                result["routing_mode"] = "parse_error"
                result["status"] = "error"
                result["message"] = "❌ CF_KV_DOMAINS 格式错误，无法解析域名列表"
                result["suggestions"].append(
                    "🔧 请检查 JSON 格式是否正确，例如: [\"example.com\"]"
                )
                return result

            # 配置成功解析
            result["configured"] = True
            result["domains"] = domains
            result["count"] = len(domains)
            result["routing_mode"] = "smart_routing"
            result["status"] = "ok"

            # 获取所有活跃域名
            active_domains = get_active_domains()

            # 检查域名有效性
            invalid_domains = []
            for domain in domains:
                # 简单的域名格式验证
                if not domain or "." not in domain:
                    invalid_domains.append(domain)

            if invalid_domains:
                result["status"] = "warning"
                result["message"] = f"⚠️ 检测到 {len(invalid_domains)} 个无效域名格式"
                result["suggestions"].append(
                    f"🔍 请检查以下域名格式: {', '.join(invalid_domains)}"
                )

            # 检查是否有域名不在活跃域名列表中
            not_in_active = [d for d in domains if d not in active_domains]
            if not_in_active:
                result["status"] = "warning"
                result["message"] = f"⚠️ {len(not_in_active)} 个域名未在自定义域名列表中"
                result["suggestions"].append(
                    f"📋 这些域名可能需要添加到 CUSTOM_DOMAINS: {', '.join(not_in_active[:3])}"
                )

            # 成功配置的消息
            if result["status"] == "ok":
                result["message"] = f"✅ 已配置 {len(domains)} 个域名使用 Cloudflare KV"
                result["suggestions"].append(
                    "💡 这些域名的邮件将通过 Cloudflare Workers KV 接收"
                )
                result["suggestions"].append(
                    "📧 其他域名将使用外部 API (mail.chatgpt.org.uk) 接收邮件"
                )
                result["suggestions"].append(
                    "🔗 配置 Email Routing: https://dash.cloudflare.com → 选择域名 → Email → Email Routing"
                )

            return result

        except Exception as e:
            result["status"] = "error"
            result["message"] = f"❌ 检查域名配置时发生错误: {str(e)}"
            result["suggestions"].append(
                "🔧 请检查配置格式并重试"
            )
            return result

    @staticmethod
    async def auto_detect_wrangler() -> Dict[str, Any]:
        """
        自动检测 Wrangler CLI 配置

        执行以下命令:
        - wrangler whoami --json (获取 Account ID)
        - wrangler kv:namespace list --json (获取 Namespace ID)

        Returns:
            检测结果字典
        """
        try:
            # 检查 Wrangler 是否安装
            version_result = await CloudflareHelper._run_command(
                ["wrangler", "--version"],
                timeout=5
            )

            if not version_result[0]:
                return {
                    "success": False,
                    "detected": False,
                    "error": "Wrangler CLI 未安装或未添加到 PATH",
                    "suggestion": "请先安装: npm install -g wrangler",
                    "fallback_hint": "✨ 即使自动检测失败，您仍可点击「📖 配置向导」按钮，获取详细的配置步骤指引"
                }

            wrangler_version = version_result[1].strip()

            # 获取 Account ID
            whoami_result = await CloudflareHelper._run_command(
                ["wrangler", "whoami"],
                timeout=10
            )

            if not whoami_result[0]:
                return {
                    "success": False,
                    "detected": False,
                    "error": "Wrangler 未登录",
                    "suggestion": "请先登录: wrangler login",
                    "wrangler_version": wrangler_version,
                    "fallback_hint": "✨ 即使自动检测失败，您仍可点击「📖 配置向导」按钮，获取详细的配置步骤指引"
                }

            # 解析 whoami 输出 (支持多种格式)
            whoami_output = whoami_result[1]
            account_id = None
            logged_in_as = None

            # 尝试多种解析方式
            for line in whoami_output.split("\n"):
                # 格式 1: "Account ID: xxx" (简单文本格式)
                if "Account ID:" in line and "│" not in line:
                    account_id = line.split("Account ID:")[-1].strip()

                # 格式 2: 表格格式 "│ xxx │ account_id │"
                if "│" in line and len(line.split("│")) >= 3:
                    parts = [p.strip() for p in line.split("│")]
                    # 检查是否是 Account ID 行 (32位十六进制)
                    for part in parts:
                        if len(part) == 32 and all(c in '0123456789abcdef' for c in part.lower()):
                            account_id = part
                            break

                # 提取登录邮箱
                if "logged in" in line.lower() or "authenticated" in line.lower():
                    # 提取邮箱 (通常在引号或括号中)
                    parts = line.split()
                    for part in parts:
                        if "@" in part:
                            logged_in_as = part.strip("'\"()[]│")
                            break

            if not account_id:
                return {
                    "success": False,
                    "detected": False,
                    "error": "无法从 wrangler whoami 输出中提取 Account ID",
                    "suggestion": "请检查 Wrangler 是否正确登录",
                    "wrangler_version": wrangler_version,
                    "fallback_hint": "✨ 即使自动检测失败，您仍可点击「📖 配置向导」按钮，获取详细的配置步骤指引"
                }

            # 获取 KV Namespaces 列表
            kv_list_result = await CloudflareHelper._run_command(
                ["wrangler", "kv", "namespace", "list"],
                timeout=10
            )

            namespace_id = None
            namespace_title = None

            if kv_list_result[0]:
                # 解析输出 (格式: JSON 或表格)
                kv_output = kv_list_result[1].strip()

                # 尝试 JSON 解析
                try:
                    if kv_output.startswith("["):
                        namespaces = json.loads(kv_output)
                        if namespaces:
                            # ⭐ 严格匹配 "EMAIL_STORAGE"
                            email_ns = next(
                                (ns for ns in namespaces if ns.get("title", "") == "EMAIL_STORAGE"),
                                None
                            )
                            if email_ns:
                                namespace_id = email_ns.get("id")
                                namespace_title = email_ns.get("title")
                            else:
                                # 找不到时返回详细错误信息
                                available_names = [ns.get("title") for ns in namespaces]
                                return {
                                    "success": False,
                                    "detected": False,
                                    "error": "未找到名为 'EMAIL_STORAGE' 的 KV Namespace",
                                    "suggestion": "请执行以下命令创建:\nwrangler kv namespace create EMAIL_STORAGE",
                                    "available_namespaces": available_names,
                                    "note": f"当前存在 {len(namespaces)} 个 namespace，但都不符合要求",
                                    "fallback_hint": "✨ 即使自动检测失败，您仍可点击「📖 配置向导」按钮，获取详细的配置步骤指引"
                                }
                        else:
                            # 没有任何 namespace
                            return {
                                "success": False,
                                "detected": False,
                                "error": "未找到任何 KV Namespace",
                                "suggestion": "请执行以下命令创建:\nwrangler kv namespace create EMAIL_STORAGE",
                                "fallback_hint": "✨ 即使自动检测失败，您仍可点击「📖 配置向导」按钮，获取详细的配置步骤指引"
                            }
                except json.JSONDecodeError:
                    # 如果不是 JSON，尝试解析表格输出
                    lines = kv_output.split("\n")
                    for line in lines:
                        if "|" in line:
                            parts = [p.strip() for p in line.split("|")]
                            if len(parts) >= 2 and parts[0] == "EMAIL_STORAGE":
                                namespace_id = parts[1]
                                namespace_title = parts[0]
                                break

                    # 表格格式也找不到
                    if not namespace_id:
                        return {
                            "success": False,
                            "detected": False,
                            "error": "未找到名为 'EMAIL_STORAGE' 的 KV Namespace",
                            "suggestion": "请执行以下命令创建:\nwrangler kv namespace create EMAIL_STORAGE",
                            "fallback_hint": "✨ 即使自动检测失败，您仍可点击「📖 配置向导」按钮，获取详细的配置步骤指引"
                        }

            await log_service.log(
                level=LogLevel.SUCCESS,
                log_type=LogType.SYSTEM,
                message="成功检测到 Wrangler CLI 配置",
                details={
                    "account_id": account_id[:8] + "...",
                    "namespace_id": namespace_id[:8] + "..." if namespace_id else None,
                    "wrangler_version": wrangler_version
                }
            )

            result = {
                "success": True,
                "detected": True,
                "data": {
                    "cf_account_id": account_id,
                    "wrangler_version": wrangler_version,
                    "logged_in_as": logged_in_as
                },
                "message": "成功检测到 Wrangler CLI 配置",
                "note": "API Token 无法自动获取，需要手动创建"
            }

            if namespace_id:
                result["data"]["cf_kv_namespace_id"] = namespace_id
                result["data"]["namespace_title"] = namespace_title
            else:
                result["warning"] = "未检测到 KV Namespace，请手动创建或填写"

            return result

        except Exception as e:
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.SYSTEM,
                message=f"Wrangler 自动检测异常: {str(e)}",
                details={
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )

            return {
                "success": False,
                "detected": False,
                "error": f"自动检测失败: {str(e)}",
                "suggestion": "请使用配置向导或手动填写",
                "fallback_hint": "✨ 即使自动检测失败，您仍可点击「📖 配置向导」按钮，获取详细的配置步骤指引"
            }

    # ==================== New: KV Namespace Utilities ====================
    @staticmethod
    async def list_kv_namespaces(account_id: str, api_token: str, search: Optional[str] = None) -> Dict[str, Any]:
        """列出 KV Namespaces（支持 search）"""
        try:
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces"
            headers = {"Authorization": f"Bearer {api_token}"}
            params = {"per_page": 100}
            if search:
                params["search"] = search

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers, params=params)
                data = resp.json()
                if resp.status_code == 200 and data.get("success"):
                    return {"success": True, "namespaces": data.get("result", [])}
                return {"success": False, "status": resp.status_code, "message": data.get("errors") or data}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    async def ensure_kv_namespace(account_id: str, api_token: str, title: str) -> Dict[str, Any]:
        """确保 namespace 存在；不存在则创建"""
        try:
            # 查找是否已存在
            listed = await CloudflareHelper.list_kv_namespaces(account_id, api_token, search=title)
            if listed.get("success"):
                for ns in listed.get("namespaces", []):
                    if ns.get("title") == title:
                        return {"success": True, "created": False, "id": ns.get("id"), "title": title}

            # 创建新 namespace
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces"
            headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
            payload = {"title": title}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                data = resp.json()
                if resp.status_code == 200 and data.get("success"):
                    rid = data.get("result", {}).get("id")
                    return {"success": True, "created": True, "id": rid, "title": title}
                return {"success": False, "status": resp.status_code, "message": data.get("errors") or data}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def build_wrangler_snippet(binding: str, namespace_id: str, preview_id: Optional[str] = None) -> str:
        """生成 wrangler.toml 片段"""
        lines = [
            "[[kv_namespaces]]",
            f"binding = \"{binding}\"",
            f"id = \"{namespace_id}\"",
        ]
        if preview_id:
            lines.append(f"preview_id = \"{preview_id}\"")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _get_enhanced_env() -> dict:
        """
        获取增强的环境变量（跨平台支持，确保能找到 Node.js 工具）

        支持平台：
        - macOS (Intel & Apple Silicon)
        - Linux
        - Windows

        Returns:
            增强后的环境变量字典
        """
        import os
        import sys
        import glob
        from pathlib import Path

        # 复制当前环境变量
        env = os.environ.copy()

        # 获取当前 PATH 和平台
        current_path = env.get("PATH", "")
        is_windows = sys.platform == "win32"
        is_macos = sys.platform == "darwin"
        path_separator = os.pathsep  # ':' on Unix, ';' on Windows

        additional_paths = []
        home = str(Path.home())

        if is_windows:
            # ==================== Windows 平台 ====================
            # 1. NVM for Windows
            nvm_home = env.get("NVM_HOME")
            if nvm_home and os.path.exists(nvm_home):
                additional_paths.append(nvm_home)

            # NVM 默认路径
            nvm_default = os.path.join(home, "AppData", "Roaming", "nvm")
            if os.path.exists(nvm_default):
                # 找到所有版本
                for version_dir in sorted(glob.glob(os.path.join(nvm_default, "v*")), reverse=True)[:3]:
                    additional_paths.append(version_dir)

            # 2. Node.js 默认安装路径
            program_files = env.get("ProgramFiles", "C:\\Program Files")
            program_files_x86 = env.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
            additional_paths.extend([
                os.path.join(program_files, "nodejs"),
                os.path.join(program_files_x86, "nodejs"),
            ])

            # 3. npm 全局路径
            appdata = env.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
            additional_paths.append(os.path.join(appdata, "npm"))

            # 4. Chocolatey
            chocolatey = env.get("ChocolateyInstall", "C:\\ProgramData\\chocolatey")
            additional_paths.append(os.path.join(chocolatey, "bin"))

            # 5. pnpm
            additional_paths.extend([
                os.path.join(appdata, "pnpm"),
                os.path.join(home, ".pnpm"),
            ])

            # 6. Volta
            volta_home = env.get("VOLTA_HOME", os.path.join(home, ".volta"))
            additional_paths.append(os.path.join(volta_home, "bin"))

        else:
            # ==================== Unix/macOS/Linux 平台 ====================
            # 1. NVM 路径（动态检测最新版本）
            nvm_base = os.path.join(home, ".nvm", "versions", "node")
            if os.path.exists(nvm_base):
                # 找到所有版本，按版本号排序（使用最新的 3 个版本）
                nvm_versions = sorted(glob.glob(os.path.join(nvm_base, "v*", "bin")), reverse=True)
                additional_paths.extend(nvm_versions[:3])

            # 2. Homebrew（macOS）
            if is_macos:
                additional_paths.extend([
                    "/opt/homebrew/bin",              # Apple Silicon
                    "/opt/homebrew/sbin",
                    "/usr/local/bin",                 # Intel Mac
                    "/usr/local/sbin",
                ])

            # 3. Linux 系统路径
            additional_paths.extend([
                "/usr/bin",
                "/usr/local/bin",
            ])

            # 4. pnpm
            additional_paths.extend([
                os.path.join(home, "Library", "pnpm") if is_macos else None,  # macOS
                os.path.join(home, ".local", "share", "pnpm"),  # Linux
            ])

            # 5. Volta
            additional_paths.append(os.path.join(home, ".volta", "bin"))

            # 6. 全局 npm
            additional_paths.extend([
                "/usr/local/lib/node_modules/.bin",
                os.path.join(home, ".npm-global", "bin"),
            ])

            # 7. Bun
            additional_paths.append(os.path.join(home, ".bun", "bin"))

            # 8. fnm (Fast Node Manager)
            additional_paths.append(os.path.join(home, ".fnm"))

        # 过滤出实际存在的路径（移除 None 和不存在的路径）
        existing_paths = [p for p in additional_paths if p and os.path.exists(p)]

        # 合并路径（去重，保持顺序）
        all_paths = existing_paths + current_path.split(path_separator)
        unique_paths = []
        seen = set()
        for p in all_paths:
            if p and p not in seen:
                unique_paths.append(p)
                seen.add(p)

        env["PATH"] = path_separator.join(unique_paths)
        return env

    @staticmethod
    async def _run_command(
        command: List[str],
        timeout: int = 10
    ) -> Tuple[bool, str]:
        """
        执行 Shell 命令（使用增强的环境变量）

        Args:
            command: 命令和参数列表
            timeout: 超时时间（秒）

        Returns:
            (是否成功, 输出内容)
        """
        try:
            # 获取增强的环境变量
            env = CloudflareHelper._get_enhanced_env()

            # 记录调试信息
            await log_service.log(
                level=LogLevel.DEBUG,
                log_type=LogType.SYSTEM,
                message=f"执行命令: {' '.join(command)}",
                details={
                    "command": command,
                    "path_preview": env.get("PATH", "")[:200] + "...",
                    "timeout": timeout
                }
            )

            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env  # ⭐ 使用增强的环境变量
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            if process.returncode == 0:
                output = stdout.decode("utf-8")
                await log_service.log(
                    level=LogLevel.DEBUG,
                    log_type=LogType.SYSTEM,
                    message=f"命令执行成功: {command[0]}",
                    details={"output_length": len(output)}
                )
                return (True, output)
            else:
                error = stderr.decode("utf-8")
                await log_service.log(
                    level=LogLevel.WARNING,
                    log_type=LogType.SYSTEM,
                    message=f"命令执行失败: {command[0]}",
                    details={
                        "returncode": process.returncode,
                        "stderr": error[:500]
                    }
                )
                return (False, error)

        except asyncio.TimeoutError:
            error_msg = f"命令执行超时 ({timeout}s)"
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.SYSTEM,
                message=error_msg,
                details={"command": command}
            )
            return (False, error_msg)
        except Exception as e:
            error_msg = f"命令执行失败: {str(e)}"
            await log_service.log(
                level=LogLevel.ERROR,
                log_type=LogType.SYSTEM,
                message=error_msg,
                details={
                    "command": command,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return (False, error_msg)


# 单例实例
cloudflare_helper = CloudflareHelper()
