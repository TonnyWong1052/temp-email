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
                "title": "创建 KV Namespace",
                "description": "进入 Workers & Pages → KV，点击「Create namespace」按钮，输入名称（如 EMAIL_STORAGE）",
                "url": "https://dash.cloudflare.com/?to=/:account/workers/kv/namespaces",
                "hint": "创建完成后，复制 Namespace ID 到下方栏位",
                "field_id": "cfKvNamespaceId",
                "icon": "📦"
            },
            {
                "id": 3,
                "title": "创建 API Token",
                "description": "点击「Create Token」，选择「Custom Token」，设置以下权限：\n• Account Settings: Read\n• Workers KV Storage: Read",
                "url": "https://dash.cloudflare.com/profile/api-tokens",
                "hint": "复制生成的 Token 到下方「API Token」栏位（只显示一次，请妥善保存）",
                "field_id": "cfApiToken",
                "icon": "🔑"
            },
            {
                "id": 4,
                "title": "检查部署环境",
                "description": "确保已安装 Node.js (v18+) 和 npm:\n\n• 检查命令: node -v && npm -v\n• 如未安装，请访问 nodejs.org 下载",
                "url": "https://nodejs.org/",
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
                "icon": "🚀",
                "command": "git clone https://github.com/TonnyWong1052/temp-email.git && cd temp-email/workers && ./deploy.sh"
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
    async def _verify_account(account_id: str, api_token: str) -> Dict[str, Any]:
        """验证 Account ID 是否正确"""
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
                            "icon": "✅"
                        }
                elif response.status_code == 403:
                    return {
                        "name": "Account ID 验证",
                        "status": "failed",
                        "message": "权限不足，请检查 API Token 是否有 'Account Settings: Read' 权限",
                        "icon": "❌"
                    }
                elif response.status_code == 404:
                    return {
                        "name": "Account ID 验证",
                        "status": "failed",
                        "message": "Account ID 不存在，请检查是否正确",
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
                    return {
                        "name": "KV Namespace 访问",
                        "status": "failed",
                        "message": "Namespace ID 不存在，请检查是否正确",
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
    async def _run_command(
        command: List[str],
        timeout: int = 10
    ) -> Tuple[bool, str]:
        """
        执行 Shell 命令

        Args:
            command: 命令和参数列表
            timeout: 超时时间（秒）

        Returns:
            (是否成功, 输出内容)
        """
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            if process.returncode == 0:
                return (True, stdout.decode("utf-8"))
            else:
                return (False, stderr.decode("utf-8"))

        except asyncio.TimeoutError:
            return (False, f"命令执行超时 ({timeout}s)")
        except Exception as e:
            return (False, f"命令执行失败: {str(e)}")


# 单例实例
cloudflare_helper = CloudflareHelper()
