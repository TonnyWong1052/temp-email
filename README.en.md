# Cloudflare Temporary Email Service

**🌐 Language / 语言**: [简体中文](README.md) | [English](README.en.md)

![GitHub stars](https://img.shields.io/github/stars/TonnyWong1052/temp-email?style=social)
![GitHub forks](https://img.shields.io/github/forks/TonnyWong1052/temp-email?style=social)
![GitHub license](https://img.shields.io/github/license/TonnyWong1052/temp-email)
![GitHub issues](https://img.shields.io/github/issues/TonnyWong1052/temp-email)

Automatically generate temporary email addresses and receive verification codes

**🌐 Live Demo**: [https://www.ogo.codes](https://www.ogo.codes)

**📚 Documentation**: [https://www.ogo.codes/docs](https://www.ogo.codes/docs)

## ✨ Features

### Core Features
- 🚀 **Fast Generation** - Randomly generate temporary email addresses
- 📧 **Receive Emails** - Automatically receive and store emails
- 🔍 **Smart Code Extraction** - Pattern learning + LLM + Regex triple extraction
- 🌐 **Custom Domains** - Support any top-level domain (TLD)
- ☁️ **Cloudflare Integration** - Receive real emails via Email Workers
- 📡 **Real-time API** - RESTful API + Long Polling support
- 📚 **Multilingual API Docs** - Swagger UI + ReDoc (English/Chinese)
- 🎨 **Web Interface** - Clean Flat Design UI
- 🌏 **Full Internationalization** - Support English and Simplified Chinese with one-click switching
- 🌍 **Online Service** - Full online demo and API service [https://www.ogo.codes](https://www.ogo.codes)

### Advanced Features ⭐️
- 🌏 **Complete i18n** - Frontend, admin panel, API docs fully multilingual
- 🧠 **Pattern Training System** - Admins can train the system to learn specific email format patterns
- 🤖 **AI Model Auto-Detection** - Automatically fetch available models from OpenAI-compatible APIs
- 🎯 **Cloudflare Auto-Configuration** - Smart detection of wrangler config, one-click connection test
- 📊 **Redis High-Traffic Support** - Distributed storage, multi-instance deployment and persistence
- 🚦 **Traffic Control** - API rate limiting, circuit breaker pattern, auto degradation protection
- 🔄 **Smart Routing** - Automatically select best email source (Cloudflare KV or external API)

## 🚀 Quick Start

### 1. Docker Deployment
```bash
docker run -d \
  --name temp-email \
  -p 1234:1234 \
  ghcr.io/tonnywong1052/temp-email:latest
```

### 2.1. Clone Repository

```bash
# Clone from GitHub
git clone https://github.com/TonnyWong1052/temp-email.git
cd temp-email
```

### 2.2. Install Dependencies

```bash
pip install -r requirements.txt
```

Or use pip-tools:

```bash
pip install -e .
```

### 2.3. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env file (optional)
```

### 2.4. Run Service

```bash
python run.py
```

Or use uvicorn:

```bash
uvicorn app.main:app --reload --port 1234
```

### 2.5. (Optional) Configure Redis for High Traffic

If you need to support high concurrency or multi-instance deployment:

```bash
# macOS
brew install redis
brew services start redis

# Ubuntu/Debian
sudo apt-get install redis-server
sudo systemctl start redis

# Docker
docker run -d -p 6379:6379 redis:latest

# Verify Redis status
redis-cli ping  # Should return PONG

# Enable Redis in .env file
echo "ENABLE_REDIS=true" >> .env
echo "REDIS_URL=redis://localhost:6379/0" >> .env
```

### 2.6. Access Service

**Local Deployment**：
- **🌐 Web Interface**: `http://localhost:1234`
  - English: `http://localhost:1234/en/`
  - Simplified Chinese: `http://localhost:1234/zh-cn/`
- **📚 API Documentation**: `http://localhost:1234/docs`
  - English: `http://localhost:1234/en/docs`
  - Simplified Chinese: `http://localhost:1234/zh-cn/docs`
  - Built-in language switcher for instant language change
- **🎯 Admin Panel**: `http://localhost:1234/admin` (Default: `admin` / `admin123`)
  - English: `http://localhost:1234/en/admin`
  - Simplified Chinese: `http://localhost:1234/zh-cn/admin`
- **📊 Logs**: `http://localhost:1234/static/logs`

**Online Demo Service** (No deployment required)：
- **🌐 Online Service**: [https://www.ogo.codes](https://www.ogo.codes)
- **📚 API Docs**: [https://www.ogo.codes/docs](https://www.ogo.codes/docs)
- **🎯 Admin Panel**: [https://www.ogo.codes/admin](https://www.ogo.codes/admin)

The online service provides full functionality including:
- ✨ Random email generation
- 📧 Real-time email reception
- 🔍 Smart code extraction (Pattern + LLM + Regex)
- 🎨 Clean web interface
- 📊 Complete API documentation
- 🧠 Pattern training system (Admin feature)

## 📖 API Usage Examples

### Generate Email

**Local Deployment**：
```bash
# Generate random email
curl -X POST http://localhost:1234/api/email/generate

# Generate email with specific domain
curl -X POST "http://localhost:1234/api/email/generate?domain=YourDomain.com"
```

Response:
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

### Get Mail List

**Local Deployment**：
```bash
curl http://localhost:1234/api/email/{token}/mails
```

**Online Service**：
```bash
curl https://www.ogo.codes/api/email/{token}/mails
```

### Extract Verification Codes

```bash
# Local service
curl http://localhost:1234/api/email/{token}/codes

# Online service
curl https://www.ogo.codes/api/email/{token}/codes
```

### Wait for New Mail (Long Polling)

```bash
# Local service
curl "http://localhost:1234/api/email/{token}/wait?timeout=60"

# Online service
curl "https://www.ogo.codes/api/email/{token}/wait?timeout=60"
```

## 🐳 Docker Deployment

### Option 0: Pull Pre-built Image (GHCR Quick Install)

```bash
# Pull multi-architecture pre-built image (linux/amd64, linux/arm64)
docker pull ghcr.io/tonnywong1052/temp-email:latest

# Run immediately (default port 1234)
docker run -d \
  --name temp-email \
  -p 1234:1234 \
  ghcr.io/tonnywong1052/temp-email:latest

# Optional: Use --env or --env-file for custom environment variables
# docker run -d --name temp-email -p 1234:1234 --env-file .env ghcr.io/tonnywong1052/temp-email:latest
```

### Option 1: Use .env File (Recommended)

```bash
# 1. Clone repository and configure environment
git clone https://github.com/TonnyWong1052/temp-email.git
cd temp-email
cp .env.example .env
# Edit .env file to configure Cloudflare API and domains

# 2. Build image
docker build -t temp-email-service .

# 3. Run container (mount .env file)
docker run -d \
  --name temp-email \
  -p 1234:1234 \
  --env-file .env \
  temp-email-service
```

### Option 2: Use Environment Variables

```bash
# Pass environment variables directly
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

### Option 3: Use docker-compose (Recommended)

```bash
# 1. Clone repository
git clone https://github.com/TonnyWong1052/temp-email.git
cd temp-email

# 2. Create .env config file
cp .env.docker .env

# 3. Edit .env file with your Cloudflare credentials
# Required fields:
#   - CF_ACCOUNT_ID=your_account_id
#   - CF_KV_NAMESPACE_ID=your_namespace_id
#   - CF_API_TOKEN=your_api_token

# 4. Start service
docker-compose up -d

# 5. View logs
docker-compose logs -f

# 6. Stop service
docker-compose down
```

### Option 4: Docker + Redis (High Traffic Deployment)

For high concurrency or multi-instance deployment with Redis as distributed storage:

```bash
# 1. Create docker-compose.yml (with Redis)
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

# 2. Start services (with Redis)
docker-compose up -d

# 3. Verify Redis connection
docker exec -it temp-email redis-cli -h redis ping  # Should return PONG

# 4. Check service status
docker-compose ps

# 5. Stop all services
docker-compose down
```

**High Traffic Deployment Benefits**：
- ✅ **Persistent Storage** - Data stored in Redis, survives service restarts
- ✅ **Horizontal Scaling** - Support multiple service instances sharing Redis
- ✅ **Traffic Control** - Built-in API rate limiting and circuit breaker protection
- ✅ **High Availability** - Redis supports master-slave replication and persistence

## ⭐️ Core Features

**1. Complete Internationalization (i18n)** ⭐️ **New Feature**

Comprehensive multilingual support:
- 🌐 **Bilingual Interface** - Support English and Simplified Chinese
- 🔄 **One-Click Switch** - Language switcher in top-right corner, instant switching without refresh
- 📚 **Multilingual API Docs** - Swagger UI and ReDoc fully translated
- 🎯 **Internationalized Admin Panel** - All configuration pages, buttons, prompts
- 💾 **Language Memory** - Auto-save user language preference (using Cookie)
- 🌍 **URL Path Recognition** - Auto-detect `/en/` and `/zh-cn/` paths

**Supported Languages**：
- 🇺🇸 English (en-US) - Full English interface
- 🇨🇳 Simplified Chinese (zh-CN) - Full Chinese interface

**Access Methods**：
```
# Web Interface
http://localhost:1234/en/       # English
http://localhost:1234/zh-cn/    # Chinese

# API Documentation
http://localhost:1234/en/docs   # English
http://localhost:1234/zh-cn/docs # Chinese

# Admin Panel
http://localhost:1234/en/admin  # English
http://localhost:1234/zh-cn/admin # Chinese
```

**2. Runtime Configuration Management**
- 🔄 **Hot Reload Support** - Some configs take effect without restart
- 📝 **Visual Editing** - Modify .env config via web interface
- 🎯 **Smart Tips** - Config items with detailed descriptions and examples
- ⚡️ **Instant Feedback** - Clearly indicates which configs need restart

**Hot-reloadable Configs**：
- Cloudflare credentials (`CF_ACCOUNT_ID`, `CF_KV_NAMESPACE_ID`, `CF_API_TOKEN`)
- Smart routing config (`CF_KV_DOMAINS`)
- Domain settings (`ENABLE_CUSTOM_DOMAINS`, `CUSTOM_DOMAINS`, `ENABLE_BUILTIN_DOMAINS`)
- LLM config (`OPENAI_API_KEY`, `OPENAI_API_BASE`, `OPENAI_MODEL`)
- Mail check interval (`MAIL_CHECK_INTERVAL`)

**Restart Required**：
- Server port and host (`PORT`, `HOST`)
- Admin account (`ADMIN_USERNAME`, `ADMIN_PASSWORD`)

**3. Pattern Training System (⭐️ Featured)**

Smart learning of verification code extraction patterns:
- 📋 **Paste Email Content** - Support any email format
- 🖱️ **Select Verification Code** - Highlight and select the code to learn
- 🧠 **Auto Learning** - System extracts contextual keywords
- 📊 **Statistics Tracking** - Record usage count and success rate
- 🎯 **Priority Matching** - Learned patterns prioritized over LLM and regex

**Learning Flow**：
```
1. Receive email → 2. Paste content to training area → 3. Select code
→ 4. Click "Learn" → 5. System saves pattern → 6. Auto-recognize in future
```

**Benefits**：
- ✅ Reduce LLM API call costs
- ✅ Improve recognition accuracy (based on real emails)
- ✅ Persistent storage (`data/patterns.json`)
- ✅ No service restart required

**4. AI Model Auto-Detection (⭐️ Featured)**

Simplified LLM configuration process:
- 🔍 **One-Click Detection** - Automatically fetch available model list
- 📋 **Dropdown Selection** - Searchable model selector + manual input
- 🌐 **Multi-API Compatible** - Support OpenAI, Anthropic and more
- 💡 **Smart Fallback** - Manual input available when API doesn't support detection

**Usage Steps**：
```
1. Fill in API Key and API Base URL
2. Click "🔍 Auto Detect" button
3. Select model from dropdown list
4. Save configuration
```

**Compatibility**：
- ✅ OpenAI standard API (`GET /v1/models`)
- ✅ Custom API response format
- ✅ 30-second timeout protection
- ✅ Detailed error messages

**5. Cloudflare Smart Configuration (⭐️ Featured)**

Simplified Cloudflare Workers configuration:
- 🎯 **Auto Detection** - Smart recognition of local wrangler config
- 📝 **Configuration Wizard** - Step-by-step guidance for Cloudflare setup
- 🔧 **One-Click Test** - Verify KV connection and permissions
- 💾 **Smart Routing** - Automatically select best email source

**Auto-Detection Features**：
- Find wrangler command in system PATH
- Read configuration from `~/.wrangler/config/`
- Extract Account ID and Namespace ID from `wrangler.toml`
- Support multiple Node.js package manager paths (npm, yarn, pnpm, bun)

**Configuration Wizard Provides**：
- Direct links to Cloudflare Dashboard
- Detailed instructions for each step
- Configuration field highlighting
- Progress tracking

**Connection Test Verification**：
- KV API connection status
- API Token permission check
- Namespace accessibility
- Detailed diagnostics and suggestions

## 🔒 Security Notes

### Data Storage
- ⚠️ **Memory Mode** (default): All data stored in memory, lost on restart
- ⚠️ **Redis Mode** (optional): Data persisted to Redis, retained after restart (requires `ENABLE_REDIS=true`)
- ⚠️ **Auto Fallback**: Automatically switches to memory mode if Redis unavailable

### Usage Limitations
- ⚠️ Emails expire after 1 hour (configurable via `EMAIL_TTL`)
- ⚠️ This service is for testing and development purposes only
- ⚠️ Do not use for receiving sensitive information
- ⚠️ Online service is for demonstration only, not for production use

### Admin Privileges
- ⚠️ Default admin account: `admin` / `admin123` (**Must change in production**)
- ⚠️ Admins can access: Config management, Pattern training, System statistics, Log viewing
- ⚠️ Recommended to set strong password via environment variable: `ADMIN_PASSWORD=your_secure_password`

### API Security
- ✅ API rate limiting support (`RATE_LIMIT_ENABLED=true`, default 60 requests/min/IP)
- ✅ Circuit breaker pattern support (`CIRCUIT_BREAKER_ENABLED=true`, prevent cascading failures)
- ✅ JWT authentication for admin endpoints (24-hour expiration)
- ✅ Customizable CORS configuration for allowed origins

## 📄 License

MIT License
