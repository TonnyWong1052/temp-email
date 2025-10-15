#!/bin/bash

# Cloudflare Email Worker 部署脚本
# 此脚本将引导您完成 Worker 部署的全部步骤

set -e  # 遇到错误立即退出

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}ℹ ${NC}$1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_header() {
    echo ""
    echo -e "${BLUE}==================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}==================================${NC}"
    echo ""
}

# 检查命令是否存在
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 检查 Node.js
print_header "步骤 1: 检查环境"

if ! command_exists node; then
    print_error "未找到 Node.js，请先安装 Node.js (v18+)"
    exit 1
fi
NODE_VERSION=$(node -v)
print_success "Node.js 已安装: $NODE_VERSION"

# 檢查 npm
if ! command_exists npm; then
    print_error "未找到 npm"
    exit 1
fi
print_success "npm 已安装"

# 检查并安装 Wrangler
print_header "步骤 2: 安装/检查 Wrangler CLI"

if ! command_exists wrangler; then
    print_info "正在安装 Wrangler CLI..."
    npm install -g wrangler
    print_success "Wrangler CLI 安装成功"
else
    WRANGLER_VERSION=$(wrangler --version)
    print_success "Wrangler 已安装: $WRANGLER_VERSION"
fi

# 登录 Cloudflare
print_header "步骤 3: 登录 Cloudflare"

print_info "即将打开浏览器进行 Cloudflare 授权..."
print_warning "如果您已经登录，可以跳过此步骤"
read -p "按 Enter 继续登录，或输入 'skip' 跳过: " SKIP_LOGIN

if [ "$SKIP_LOGIN" != "skip" ]; then
    wrangler login
    print_success "Cloudflare 登录成功"
else
    print_info "跳过登录步骤"
fi

# 创建 KV Namespace
print_header "步骤 4: 创建 Workers KV Namespace"

# 首先检查是否已存在 namespace
print_info "检查现有的 KV namespaces..."
EXISTING_NS=$(wrangler kv namespace list 2>&1)

# 尝试从现有 namespace 列表中提取 ID
if echo "$EXISTING_NS" | grep -q "EMAIL_STORAGE"; then
    print_success "发现已存在的 EMAIL_STORAGE namespace"
    
    # 尝试多种格式提取 ID
    # 格式1: JSON 输出 {"id": "xxx", "title": "EMAIL_STORAGE"}
    KV_NAMESPACE_ID=$(echo "$EXISTING_NS" | grep -o '"id": "[^"]*"' | head -1 | grep -o '[a-f0-9]\{32\}')
    
    # 格式2: 表格输出或其他格式
    if [ -z "$KV_NAMESPACE_ID" ]; then
        KV_NAMESPACE_ID=$(echo "$EXISTING_NS" | grep "EMAIL_STORAGE" | grep -o '[a-f0-9]\{32\}' | head -1)
    fi
    
    if [ -n "$KV_NAMESPACE_ID" ]; then
        print_success "使用现有 Namespace ID: $KV_NAMESPACE_ID"
    fi
else
    # Namespace 不存在，创建新的
    print_info "正在创建新的 Workers KV namespace..."
    print_info "命令: wrangler kv namespace create EMAIL_STORAGE"
    
    KV_OUTPUT=$(wrangler kv namespace create EMAIL_STORAGE 2>&1)
    echo "$KV_OUTPUT"
    
    # 尝试多种格式提取 namespace ID
    # 格式1: id = "xxx" (TOML 格式)
    KV_NAMESPACE_ID=$(echo "$KV_OUTPUT" | grep -o 'id = "[^"]*"' | grep -o '"[^"]*"' | tr -d '"')
    
    # 格式2: "id": "xxx" (JSON 格式)
    if [ -z "$KV_NAMESPACE_ID" ]; then
        KV_NAMESPACE_ID=$(echo "$KV_OUTPUT" | grep -o '"id"[[:space:]]*:[[:space:]]*"[^"]*"' | grep -o '"[a-f0-9]\{32\}"' | tr -d '"')
    fi
    
    # 格式3: 直接匹配 32 位十六进制字符串
    if [ -z "$KV_NAMESPACE_ID" ]; then
        KV_NAMESPACE_ID=$(echo "$KV_OUTPUT" | grep -o '[a-f0-9]\{32\}' | head -1)
    fi
    
    if [ -n "$KV_NAMESPACE_ID" ]; then
        print_success "KV Namespace 创建成功"
        print_info "Namespace ID: $KV_NAMESPACE_ID"
    fi
fi

# 如果所有自动提取方法都失败，提示手动输入
if [ -z "$KV_NAMESPACE_ID" ]; then
    print_warning "无法自动提取 KV Namespace ID"
    print_info "请手动输入 Namespace ID（32位十六进制字符串）："
    print_info "提示：运行 'wrangler kv namespace list' 查看所有 namespaces"
    echo ""
    read -p "Namespace ID: " KV_NAMESPACE_ID
    
    # 验证 ID 格式
    if [[ ! "$KV_NAMESPACE_ID" =~ ^[a-f0-9]{32}$ ]]; then
        print_error "无效的 Namespace ID 格式（应为32位十六进制字符串）"
        exit 1
    fi
    
    print_success "已接收 Namespace ID: $KV_NAMESPACE_ID"
fi

# 更新 wrangler.toml
print_header "步骤 5: 更新 wrangler.toml 配置"

# 备份原文件
cp wrangler.toml wrangler.toml.backup
print_success "已备份 wrangler.toml → wrangler.toml.backup"

# 替换 namespace ID
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    sed -i '' "s/YOUR_KV_NAMESPACE_ID/$KV_NAMESPACE_ID/g" wrangler.toml
else
    # Linux
    sed -i "s/YOUR_KV_NAMESPACE_ID/$KV_NAMESPACE_ID/g" wrangler.toml
fi
print_success "wrangler.toml 已更新"

# 显示配置
print_info "当前配置："
grep -A 2 "kv_namespaces" wrangler.toml

# 部署 Worker
print_header "步骤 6: 部署 Email Worker"

print_info "正在部署 Worker 到 Cloudflare..."
DEPLOY_OUTPUT=$(wrangler deploy 2>&1)
echo "$DEPLOY_OUTPUT"

# 检查部署是否成功 (wrangler v4 使用 "Deployed" 而不是 "Success")
if echo "$DEPLOY_OUTPUT" | grep -qE "(Deployed|Success)"; then
    print_success "Worker 部署成功！"

    # 提取 Worker URL
    WORKER_URL=$(echo "$DEPLOY_OUTPUT" | grep -o 'https://[^ ]*workers.dev[^ ]*' | head -1)
    if [ -n "$WORKER_URL" ]; then
        print_info "Worker URL: $WORKER_URL"
    fi
else
    print_error "Worker 部署失败"
    exit 1
fi

# 保存配置信息
print_header "步骤 7: 保存配置信息"

CONFIG_FILE="../.cloudflare_config"
cat > "$CONFIG_FILE" << EOF
# Cloudflare 配置信息
# 生成时间: $(date)

CF_KV_NAMESPACE_ID=$KV_NAMESPACE_ID
WORKER_URL=$WORKER_URL

# 请到 Cloudflare Dashboard 获取：
# 1. Account ID: https://dash.cloudflare.com/ (右侧边栏)
# 2. API Token: https://dash.cloudflare.com/profile/api-tokens
#    - 创建 Token 时选择 "Edit Cloudflare Workers" 模板
#    - 权限需要包含: Workers KV Storage (Read)
EOF

print_success "配置信息已保存到: $CONFIG_FILE"

# 完成总结
print_header "✨ 部署完成！"

print_success "Email Worker 已成功部署到 Cloudflare"
echo ""
print_info "下一步操作："
echo "  1. 前往 Cloudflare Dashboard 获取 Account ID"
echo "     访问: https://dash.cloudflare.com/"
echo ""
echo "  2. 创建 API Token"
echo "     访问: https://dash.cloudflare.com/profile/api-tokens"
echo "     使用 'Edit Cloudflare Workers' 模板"
echo ""
echo "  3. 配置 Email Routing"
echo "     • 在 Cloudflare Dashboard 选择您的域名"
echo "     • 进入 Email → Email Routing"
echo "     • 点击「启用电子邮件路由」(Enable Email Routing)"
echo "     • 启用后，点击「路由规则」(Routing rules) 选项卡"
echo "     • 找到 Catch-All 规则，点击「编辑」(Edit)"
echo "     • 在「操作」下拉菜单中选择「发送到 Worker」"
echo "     • 选择 Worker: temp-email-worker"
echo "     • 点击保存"
echo ""
echo "  4. 更新项目 .env 文件"
echo "     USE_CLOUDFLARE_KV=true"
echo "     CF_ACCOUNT_ID=<您的 Account ID>"
echo "     CF_KV_NAMESPACE_ID=$KV_NAMESPACE_ID"
echo "     CF_API_TOKEN=<您的 API Token>"
echo ""
echo "详细配置指南: ../docs/CLOUDFLARE_SETUP_GUIDE.md"
echo ""
print_success "所有步骤已完成！"
