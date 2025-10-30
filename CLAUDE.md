# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A FastAPI-based temporary email service that generates disposable email addresses, receives emails, and automatically extracts verification codes. Uses in-memory storage with optional Redis support and Cloudflare Workers KV integration.

## Development Commands

### Running the Application

```bash
# Start development server with auto-reload
python run.py

# Enable debug mode for detailed email fetching logs
python run.py --debug

# Alternative: using uvicorn directly
uvicorn app.main:app --reload --port 1234
```

### Testing

```bash
# Run pytest test suite
python -m pytest tests/

# Run standalone integration tests
python test_kv_integration.py        # Test Cloudflare KV integration
python test_custom_domains.py        # Test custom domains configuration
python test_email_api_direct.py      # Test external API connection
python test_redis_integration.py     # Test Redis integration
```

### Dependencies

```bash
# Install dependencies (exact versions pinned)
pip install -r requirements.txt

# Core dependencies:
# - fastapi==0.109.0
# - uvicorn[standard]==0.27.0
# - pydantic==2.5.3
# - httpx==0.26.0
# - redis==5.0.1 (optional, for high traffic)
```

## Architecture

### Service Layer Pattern

The application follows a clean service-oriented architecture:

```
app/
├── main.py              # FastAPI app initialization, lifespan management
├── config.py            # Settings (Pydantic Settings), domain configuration
├── models.py            # Pydantic models (Email, Mail, Code, API responses)
├── routers/
│   ├── email.py         # Email/mail endpoints
│   ├── system.py        # System endpoints (domains, health, test)
│   ├── admin.py         # Admin authentication and configuration
│   └── pattern.py       # Pattern management API
├── services/
│   ├── email_service.py        # Email generation, validation
│   ├── mail_service.py         # Mail fetching (multi-source: KV or external API)
│   ├── kv_mail_service.py      # Cloudflare Workers KV client
│   ├── code_service.py         # Verification code extraction
│   ├── storage_service.py      # In-memory storage with expiration
│   ├── redis_storage_service.py # Redis distributed storage
│   └── llm_code_service.py     # LLM-based code extraction
└── middleware/
    └── logging_middleware.py   # HTTP request/response logging
```

### Key Design Patterns

**Singleton Services**: All services are instantiated as singletons at module level for shared state.

**Multi-Source Mail Fetching**: Intelligent routing between Cloudflare Workers KV (for custom domains) and external API (for builtin domains).

**Verification Code Extraction**: Three-tier strategy - Pattern-based → LLM-based → Regex-based with cascading fallback.

**Smart Routing**: Domain-based routing automatically chooses between Cloudflare KV and external API based on configuration.

## Configuration

Settings are loaded via Pydantic Settings from `.env` file:

```python
# Server Configuration
PORT = 1234
HOST = "0.0.0.0"
RELOAD = true

# Email Service Configuration
EMAIL_TTL = 3600                    # Email expiration (seconds)
MAIL_CHECK_INTERVAL = 10            # Polling interval (seconds)

# Redis Configuration (Optional, for High Traffic)
ENABLE_REDIS = false
REDIS_URL = "redis://localhost:6379/0"

# Cloudflare Workers KV (Optional)
USE_CLOUDFLARE_KV = false
CF_ACCOUNT_ID = ""
CF_KV_NAMESPACE_ID = ""
CF_API_TOKEN = ""

# Domain Configuration
ENABLE_CUSTOM_DOMAINS = true
ENABLE_BUILTIN_DOMAINS = true

# LLM Code Extraction
USE_LLM_EXTRACTION = true
OPENAI_API_KEY = ""
OPENAI_API_BASE = "https://api.longcat.chat/openai/v1"
OPENAI_MODEL = "LongCat-Flash-Chat"
```

## Important Features

### Multi-Source Mail Fetching

The service supports intelligent domain-based routing:

1. **Cloudflare Workers KV** - For custom domains with real email routing
2. **External API** - For builtin domains using proven external service

Routing logic in `app/config.py:should_use_cloudflare_kv()` determines source based on domain and `CF_KV_DOMAINS` configuration.

### Verification Code Detection

Triple extraction strategy with cascading fallback:

1. **Pattern-based** - Learned patterns from admin training
2. **LLM-based** - OpenAI-compatible API for intelligent extraction
3. **Regex-based** - Multiple patterns with confidence scoring

### Admin Dashboard

Accessible at `http://localhost:1234/admin` with:
- Runtime configuration management
- Cloudflare auto-detection and wizard
- AI model auto-detection
- Pattern training system
- System statistics and log viewing

Default credentials: `admin` / `admin123` (change in production)

## API Endpoints

**Email Management**:
- `POST /api/email/generate` - Generate temporary email
- `GET /api/email/{token}/mails` - Fetch mail list
- `GET /api/email/{token}/codes` - Extract verification codes
- `GET /api/email/{token}/wait` - Wait for new mail (long polling)

**System**:
- `GET /api/domains` - Get available domains
- `GET /api/health` - Health check
- `GET /test` - Test Cloudflare KV connection

## Storage Modes

- **In-Memory Mode** (default): Data lost on restart
- **Redis Mode** (`ENABLE_REDIS=true`): Persistent storage, supports multiple instances
- **Automatic Fallback**: Falls back to in-memory if Redis unavailable

## Testing and Debugging

**Debug Mode**:
```bash
python run.py --debug
# or set DEBUG_EMAIL_FETCH=true in .env
```

**Manual API Testing**:
```bash
# Generate email
curl -X POST http://localhost:1234/api/email/generate

# Test KV connection
curl http://localhost:1234/test

# Check domains
curl http://localhost:1234/api/domains
```

## Docker Deployment

```bash
# Quick start with pre-built image
docker run -d --name temp-email -p 1234:1234 ghcr.io/tonnywong1052/temp-email:latest

# Or build locally
docker build -t temp-email-service .
docker run -p 1234:1234 temp-email-service
```

## Important Design Decisions

**Why multi-source mail fetching**: Allows gradual migration from external API to self-hosted Cloudflare solution.

**Why singleton services**: Shared in-memory state requires single instance per process.

**Why 1-hour expiration**: Balances temporary email use case with memory constraints.

**Why pattern learning**: Reduces LLM API costs and improves accuracy for known email formats.