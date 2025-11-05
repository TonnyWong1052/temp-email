# Cloudflare 临时邮箱服务 (Temporary Email Service)

**🌐 语言 / Language**: [简体中文](README.md) | [English](README.en.md)

![GitHub stars](https://img.shields.io/github/stars/TonnyWong1052/temp-email?style=social)
![GitHub forks](https://img.shields.io/github/forks/TonnyWong1052/temp-email?style=social)
![GitHub license](https://img.shields.io/github/license/TonnyWong1052/temp-email)
![GitHub issues](https://img.shields.io/github/issues/TonnyWong1052/temp-email)

自动生成临时邮箱并接收验证码的服务

**🌐 在线演示**: [https://www.ogo.codes](https://www.ogo.codes)

**📚 在线文档**: [https://www.ogo.codes/docs](https://www.ogo.codes/docs)

## ✨ 特性

### 核心功能
- 🚀 **快速生成** - 随机生成临时邮箱地址
- 📧 **接收邮件** - 自动接收并存储邮件
- 🔍 **智能验证码提取** - Pattern学习 + LLM + 正则表达式三重提取
- 🌐 **自定义域名** - 支持使用任意顶级域名（TLD）
- ☁️ **Cloudflare 整合** - 通过 Email Workers 接收真实邮件
- 📡 **实时API** - RESTful API + 长轮询支持
- 📚 **多语言API文档** - Swagger UI + ReDoc（支持英文/简体中文）
- 🎨 **Web界面** - 简洁的Flat Design风格界面
- 🌏 **完整国际化** - 支持英文和简体中文，一键切换
- 🌍 **在线服务** - 提供完整的在线演示和API服务 [https://www.ogo.codes](https://www.ogo.codes)

### 进阶功能 ⭐️
- 🌏 **完整国际化 (i18n)** - 前端界面、管理后台、API 文档全面支持多语言切换
- 🧠 **Pattern 训练系统** - 管理员可训练系统学习特定邮件格式的验证码提取模式
- 🤖 **AI 模型自动检测** - 自动获取 OpenAI 兼容 API 的可用模型列表
- 🎯 **Cloudflare 自动配置** - 智能检测 wrangler 配置，一键测试连接
- 📊 **Redis 高流量支持** - 分布式存储，支持多实例部署和持久化
- 🚦 **流量控制** - API 限流、断路器模式，自动降级保护
- 🔄 **智能路由** - 自动选择最佳邮件来源（Cloudflare KV 或外部 API）

## 🚀 快速开始

### 1. Docker部署
```bash
docker run -d \
  --name temp-email \
  -p 1234:1234 \
  ghcr.io/tonnywong1052/temp-email:latest
```

### 2.1. 克隆倉庫

```bash
# 從 GitHub 克隆倉庫
git clone https://github.com/TonnyWong1052/temp-email.git
cd temp-email
```

### 2.2. 安装依赖

```bash
pip install -r requirements.txt
```

或使用 pip-tools:

```bash
pip install -e .
```

### 2.3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件（可选）
```

### 2.4. 运行服务

```bash
python run.py
```

或使用 uvicorn:

```bash
uvicorn app.main:app --reload --port 1234
```

### 2.5. （可选）配置 Redis 高流量支持

如果需要支持高并发访问或多实例部署：

```bash
# macOS
brew install redis
brew services start redis

# Ubuntu/Debian
sudo apt-get install redis-server
sudo systemctl start redis

# Docker
docker run -d -p 6379:6379 redis:latest

# 验证 Redis 运行状态
redis-cli ping  # 应返回 PONG

# 在 .env 文件中启用 Redis
echo "ENABLE_REDIS=true" >> .env
echo "REDIS_URL=redis://localhost:6379/0" >> .env
```

### 2.6. 访问服务

**本地部署访问**：
- **🌐 Web 界面**: `http://localhost:1234`
  - 英文版：`http://localhost:1234/en/`
  - 简体中文：`http://localhost:1234/zh-cn/`
- **📚 API 文档**: `http://localhost:1234/docs`
  - 英文版：`http://localhost:1234/en/docs`
  - 简体中文：`http://localhost:1234/zh-cn/docs`
  - 文档内置语言切换器，可随时切换
- **🎯 管理后台**: `http://localhost:1234/admin` (默认账号: `admin` / `admin123`)
  - 英文版：`http://localhost:1234/en/admin`
  - 简体中文：`http://localhost:1234/zh-cn/admin`
- **📊 日志查看**: `http://localhost:1234/static/logs`

**在线演示服务**（无需部署）：
- **🌐 在线服务**: [https://www.ogo.codes](https://www.ogo.codes)
- **📚 API文档**: [https://www.ogo.codes/docs](https://www.ogo.codes/docs)
- **🎯 管理后台**: [https://www.ogo.codes/admin](https://www.ogo.codes/admin)

在线服务提供了完整的功能演示，包括：
- ✨ 随机邮箱生成
- 📧 实时邮件接收
- 🔍 智能验证码提取（Pattern + LLM + 正则）
- 🎨 简洁的Web界面
- 📊 完整的API文档
- 🧠 Pattern 训练系统（管理员功能）

## 📖 API使用示例

### 生成邮箱

**本地部署示例**：
```bash
# 生成随机邮箱
curl -X POST http://localhost:1234/api/email/generate

# 生成指定域名的邮箱
curl -X POST "http://localhost:1234/api/email/generate?domain=YourDomain.com"
```

响应:
```json
{
  "success": true,
  "data": {
    "email": "abc123@yourDomain.com",
    "token": "unique-token-here",
    "createdAt": "2025-10-11T14:21:03Z",
    "expiresAt": "2025-10-11T15:21:03Z",
    "webUrl": null,
    "useCloudflareKV": true
  }
}
```

### 获取邮件列表

**本地部署示例**：
```bash
curl http://localhost:1234/api/email/{token}/mails
```

**在线服务示例**：
```bash
curl https://www.ogo.codes/api/email/{token}/mails
```

### 提取验证码

```bash
# 本地服务
curl http://localhost:1234/api/email/{token}/codes

# 在线服务
curl https://www.ogo.codes/api/email/{token}/codes
```

### 等待新邮件 (长轮询)

```bash
# 本地服务
curl "http://localhost:1234/api/email/{token}/wait?timeout=60"

# 在线服务
curl "https://www.ogo.codes/api/email/{token}/wait?timeout=60"
```

### Cloudflare Email Workers 整合

#### Cloudflare 配置

##### 配置向导

我們提供了智能配置向導，幫助您快速完成 Cloudflare 設置：

- 🎯 **自動檢測** - 系統自動檢測您的 Cloudflare 環境
- 📝 **逐步引導** - 通過 Web 界面完成所有配置步驟
- 🔧 **一鍵測試** - 實時驗證配置是否正確
- 📋 **配置清單** - 提供完整的配置項檢查清單

**訪問方式**：
- 本地部署：`http://localhost:1234/admin/cloudflare/wizard`
- 在線服務：`https://www.ogo.codes/admin/cloudflare/wizard`

**配置步驟**：
1. 準備 Cloudflare Account ID 和 API Token
2. 創建 KV 命名空間
3. 配置域名 MX 記錄
4. 部署 Email Workers
5. 測試郵件接收功能

#### 🎯 架构优势
- ✅ **接收真实邮件** - 任何发送到您域名的邮件
- ✅ **完全免费** - Cloudflare 免费方案涵盖所有功能
- ✅ **自动过期** - 邮件1小时后自动清理
- ✅ **高可靠性** - Cloudflare 全球基础设施
- ✅ **低延迟** - CDN加速，全球访问快速

## 🐳 Docker部署

### 方式0：直接拉取预构建镜像（GHCR 快速安装）

```bash
# 拉取多架构预构建镜像（linux/amd64, linux/arm64）
docker pull ghcr.io/tonnywong1052/temp-email:latest

# 立即运行（默认端口 1234）
docker run -d \
  --name temp-email \
  -p 1234:1234 \
  ghcr.io/tonnywong1052/temp-email:latest

# 可选：如需自定义环境变量，使用 --env 或 --env-file 挂载
# docker run -d --name temp-email -p 1234:1234 --env-file .env ghcr.io/tonnywong1052/temp-email:latest
```

输出示例：

```
main: Pulling from tonnywong1052/temp-email
e363695fcb93: Already exists
c649c88aa374: Already exists
...
Status: Downloaded newer image for ghcr.io/tonnywong1052/temp-email:latest
ghcr.io/tonnywong1052/temp-email:latest
```

### 方式一：使用 .env 文件（推荐）

```bash
# 1. 克隆仓库并配置环境变量
git clone https://github.com/TonnyWong1052/temp-email.git
cd temp-email
cp .env.example .env
# 编辑 .env 文件，配置 Cloudflare API 和域名

# 2. 构建镜像
docker build -t temp-email-service .

# 3. 运行容器（挂载 .env 文件）
docker run -d \
  --name temp-email \
  -p 1234:1234 \
  --env-file .env \
  temp-email-service
```

### 方式二：使用环境变量

```bash
# 直接传递环境变量
docker run -d \
  --name temp-email \
  -p 1234:1234 \
  -e PORT=1234 \
  -e USE_CLOUDFLARE_KV=true \
  -e CF_ACCOUNT_ID=your_account_id \
  -e CF_KV_NAMESPACE_ID=your_namespace_id \
  -e CF_API_TOKEN=your_api_token \
  -e ENABLE_CUSTOM_DOMAINS=true \
  -e CUSTOM_DOMAINS='["example.com"]' \
  temp-email-service
```

### 方式三：使用 docker-compose（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/TonnyWong1052/temp-email.git
cd temp-email

# 2. 创建 .env 配置文件
cp .env.docker .env

# 3. 编辑 .env 文件，填写你的 Cloudflare 凭据
# 必填项：
#   - CF_ACCOUNT_ID=your_account_id
#   - CF_KV_NAMESPACE_ID=your_namespace_id
#   - CF_API_TOKEN=your_api_token

# 4. 启动服务
docker-compose up -d

# 5. 查看日志
docker-compose logs -f

# 6. 停止服务
docker-compose down
```

### 方式四：Docker + Redis（高流量部署）

如需支持高并发或多实例部署，可使用 Redis 作为分布式存储：

```bash
# 1. 创建 docker-compose.yml（包含 Redis）
cat > docker-compose.yml <<EOF
version: '3.8'

services:
  temp-email:
    image: ghcr.io/tonnywong1052/temp-email:latest
    ports:
      - "1234:1234"
    environment:
      - ENABLE_REDIS=true
      - REDIS_URL=redis://redis:6379/0
      - RATE_LIMIT_ENABLED=true
      - RATE_LIMIT_PER_MINUTE=60
      - CIRCUIT_BREAKER_ENABLED=true
    depends_on:
      - redis
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  redis_data:
EOF

# 2. 启动服务（含 Redis）
docker-compose up -d

# 3. 验证 Redis 连接
docker exec -it temp-email redis-cli -h redis ping  # 应返回 PONG

# 4. 查看服务状态
docker-compose ps

# 5. 停止所有服务
docker-compose down
```

**高流量部署优势**：
- ✅ **持久化存储** - 数据存储在 Redis，服务重启不丢失
- ✅ **水平扩展** - 支持多个服务实例共享同一 Redis
- ✅ **流量控制** - 内置 API 限流和断路器保护
- ✅ **高可用** - Redis 支持主从复制和持久化

#### 🔧 Docker 环境配置说明

**⚠️ 重要：配置优先级**
```
Docker 环境变量 > .env 文件 > 默认值
```

**配置方法对比**：

| 方法 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| `.env` 文件 | 易于管理，支持版本控制 | 需要重启容器才能生效 | 开发环境，配置较少改动 |
| 环境变量 | 灵活，支持 CI/CD | 命令行较长，难以管理 | 生产环境，自动化部署 |
| docker-compose | 配置集中，易于维护 | 需要额外文件 | 推荐用于生产环境 |

**Admin 界面配置注意事项**：

在 Docker 环境中，通过 Admin 界面（`/admin`）修改配置时：

1. **即时生效的配置**（无需重启）：
   - Cloudflare KV 凭据
   - 域名设置
   - LLM API 配置
   - 邮件检查间隔

2. **需要重启的配置**：
   - 服务器端口和主机
   - 管理员账户信息

3. **配置持久化**：
   - Admin 界面修改的配置会保存到容器内的 `.env` 文件
   - **⚠️ 如果容器重启，配置会丢失**（除非挂载了 volume）
   - 建议使用 docker-compose 的 `.env` 文件进行持久化配置

**示例：通过 .env 文件配置 Cloudflare KV**

```env
# .env 文件内容
USE_CLOUDFLARE_KV=true
CF_ACCOUNT_ID=1234567890abcdef
CF_KV_NAMESPACE_ID=abcdef1234567890
CF_API_TOKEN=your_api_token_here
CF_KV_DOMAINS='["example.com"]'

ENABLE_CUSTOM_DOMAINS=true
CUSTOM_DOMAINS='["example.com"]'
ENABLE_BUILTIN_DOMAINS=true

ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password
```

然后使用 docker-compose 启动：
```bash
docker-compose up -d
```

**默认凭据**（⚠️ 生产环境务必修改）:
- 用户名: `admin`
- 密码: `admin123`

#### ⭐️ 核心功能

**1. 完整国际化支持 (i18n)** ⭐️ **新功能**

全面的多语言支持：
- 🌐 **双语界面** - 支持英文 (English) 和简体中文
- 🔄 **一键切换** - 界面右上角语言切换器，实时切换无需刷新
- 📚 **API 文档多语言** - Swagger UI 和 ReDoc 完整翻译
- 🎯 **管理后台国际化** - 所有配置界面、按钮、提示信息
- 💾 **语言记忆** - 自动保存用户语言偏好（使用 Cookie）
- 🌍 **URL 路径识别** - 自动识别 `/en/` 和 `/zh-cn/` 路径

**支持的语言版本**：
- 🇺🇸 English (en-US) - 完整英文界面
- 🇨🇳 简体中文 (zh-CN) - 完整中文界面

**访问方式**：
```
# Web 界面
http://localhost:1234/en/       # 英文版
http://localhost:1234/zh-cn/    # 中文版

# API 文档
http://localhost:1234/en/docs   # 英文版
http://localhost:1234/zh-cn/docs # 中文版

# 管理后台
http://localhost:1234/en/admin  # 英文版
http://localhost:1234/zh-cn/admin # 中文版
```

**2. 运行时配置管理**
- 🔄 **热重载支持** - 部分配置无需重启即可生效
- 📝 **可视化编辑** - 通过 Web 界面修改 .env 配置
- 🎯 **智能提示** - 配置项带有详细说明和示例
- ⚡️ **即时反馈** - 清晰标识哪些配置需要重启

**可热重载的配置**：
- Cloudflare 凭据（`CF_ACCOUNT_ID`, `CF_KV_NAMESPACE_ID`, `CF_API_TOKEN`）
- 智能路由配置（`CF_KV_DOMAINS`）
- 域名设置（`ENABLE_CUSTOM_DOMAINS`, `CUSTOM_DOMAINS`, `ENABLE_BUILTIN_DOMAINS`）
- LLM 配置（`OPENAI_API_KEY`, `OPENAI_API_BASE`, `OPENAI_MODEL`）
- 邮件检查间隔（`MAIL_CHECK_INTERVAL`）

**需重启的配置**：
- 服务器端口和主机（`PORT`, `HOST`）
- 管理员账户（`ADMIN_USERNAME`, `ADMIN_PASSWORD`）

**3. Pattern 训练系统（⭐️ 特色功能）**

智能学习验证码提取模式：
- 📋 **粘贴邮件内容** - 支持任意邮件格式
- 🖱️ **选中验证码** - 高亮选择要学习的验证码
- 🧠 **自动学习** - 系统提取上下文关键词
- 📊 **统计追踪** - 记录使用次数和成功率
- 🎯 **优先匹配** - 已学习模式优先于 LLM 和正则

**学习流程**：
```
1. 接收邮件 → 2. 粘贴内容到训练区 → 3. 选中验证码
→ 4. 点击「学习」 → 5. 系统保存模式 → 6. 未来自动识别
```

**优势**：
- ✅ 降低 LLM API 调用成本
- ✅ 提高识别准确率（基于真实邮件）
- ✅ 持久化存储（`data/patterns.json`）
- ✅ 无需重启服务

**4. AI 模型自动检测（⭐️ 特色功能）**

简化 LLM 配置流程：
- 🔍 **一键检测** - 自动获取可用模型列表
- 📋 **下拉选择** - 可搜索的模型选择器 + 手动输入
- 🌐 **多 API 兼容** - 支持 OpenAI、Anthropic 等多种格式
- 💡 **智能后备** - API 不支持时可手动输入模型名

**使用步骤**：
```
1. 填写 API Key 和 API Base URL
2. 点击「🔍 自动检测」按钮
3. 从下拉列表选择模型
4. 保存配置
```

**兼容性**：
- ✅ OpenAI 标准 API (`GET /v1/models`)
- ✅ 自定义 API 响应格式
- ✅ 30秒超时保护
- ✅ 详细错误提示

**5. Cloudflare 智能配置（⭐️ 特色功能）**

简化 Cloudflare Workers 配置：
- 🎯 **自动检测** - 智能识别本地 wrangler 配置
- 📝 **配置向导** - 逐步引导完成 Cloudflare 设置
- 🔧 **一键测试** - 验证 KV 连接和权限
- 💾 **智能路由** - 自动选择最佳邮件来源

**自动检测功能**：
- 查找系统 PATH 中的 wrangler 命令
- 读取 `~/.wrangler/config/` 配置文件
- 提取 `wrangler.toml` 中的 Account ID 和 Namespace ID
- 支持多种 Node.js 包管理器路径（npm, yarn, pnpm, bun）

**配置向导提供**：
- 直达 Cloudflare Dashboard 的链接
- 每一步的详细说明
- 配置项字段高亮提示
- 进度追踪

**连接测试验证**：
- KV API 连接状态
- API Token 权限检查
- Namespace 可访问性
- 详细诊断信息和建议

## 🚀 部署信息

### 在线服务

我们提供了完整的在线部署版本，您可以直接使用：

- **🌐 服务地址**: [https://www.ogo.codes](https://www.ogo.codes)
- **📚 API文档**: [https://www.ogo.codes/docs](https://www.ogo.codes/docs)
- **🎯 管理后台**: [https://www.ogo.codes/admin](https://www.ogo.codes/admin)

在线服务特性：
- ✅ 完整功能演示
- ✅ 无需注册或登录
- ✅ 实时邮件接收
- ✅ 智能验证码提取
- ✅ 完整API文档
- ✅ 响应式Web界面

### 本地部署

如果您需要自定义部署，请参考上方的「快速开始」和「Docker部署」部分。

## 🔒 安全说明

### 数据存储
- ⚠️ **内存模式**（默认）：所有数据存储在内存中，重启后丢失
- ⚠️ **Redis 模式**（可选）：数据持久化到 Redis，重启后保留（需配置 `ENABLE_REDIS=true`）
- ⚠️ **自动降级**：Redis 不可用时自动切换到内存模式

### 使用限制
- ⚠️ 邮箱1小时后自动过期（可配置 `EMAIL_TTL`）
- ⚠️ 此服务仅用于测试和开发目的
- ⚠️ 请勿用于接收敏感信息
- ⚠️ 在线服务仅供演示，请勿用于生产环境

### 管理员权限
- ⚠️ 默认管理员账号：`admin` / `admin123`（**生产环境务必修改**）
- ⚠️ 管理员可访问：配置管理、Pattern 训练、系统统计、日志查看
- ⚠️ 建议通过环境变量设置强密码：`ADMIN_PASSWORD=your_secure_password`

### API 安全
- ✅ 支持 API 限流（`RATE_LIMIT_ENABLED=true`，默认 60 请求/分钟/IP）
- ✅ 支持断路器模式（`CIRCUIT_BREAKER_ENABLED=true`，防止级联故障）
- ✅ JWT 认证保护管理员端点（24小时过期）
- ✅ CORS 配置可自定义允许的来源

## 📄 License

MIT License