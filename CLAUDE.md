# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A FastAPI-based temporary email service that generates disposable email addresses, receives emails, and automatically extracts verification codes. Uses in-memory storage (no database required) with automatic expiration after 1 hour.

## Development Commands

### Running the Application

```bash
# Start development server with auto-reload
python run.py

# Alternative: using uvicorn directly
uvicorn app.main:app --reload --port 1234
```

### Testing & Integration Tests

```bash
# Run pytest test suite
python -m pytest tests/

# Run specific integration tests
python test_kv_integration.py        # Test Cloudflare KV integration
python test_custom_domains.py        # Test custom domains configuration

# Test API endpoints
curl http://localhost:1234/test      # Test Cloudflare KV connection
curl http://localhost:1234/api/health    # Health check
curl http://localhost:1234/api/domains   # List available domains
```

### Cloudflare Workers Deployment

```bash
# Install Wrangler CLI
npm install -g wrangler

# Login to Cloudflare
wrangler login

# Create KV namespace
cd workers
wrangler kv:namespace create EMAIL_STORAGE

# Deploy Email Worker
wrangler deploy

# View Worker logs
wrangler tail
```

### Dependencies

```bash
# Install dependencies (exact versions pinned)
pip install -r requirements.txt

# Core dependencies (from requirements.txt):
# - fastapi==0.109.0
# - uvicorn[standard]==0.27.0
# - pydantic==2.5.3
# - pydantic-settings==2.1.0
# - httpx==0.26.0
# - python-dotenv==1.0.0
# - python-jose[cryptography]==3.3.0  # JWT authentication
# - passlib[bcrypt]==1.7.4            # Password hashing
```

### Testing

```bash
# Run all tests
python -m pytest tests/

# Run specific test files
python -m pytest tests/test_mail_service_external_parsing.py
python -m pytest tests/test_maileroo_integration.py

# Run with verbose output
python -m pytest -v tests/
```

### Docker

```bash
# Build and run
docker build -t temp-email-service .
docker run -p 8000:8000 temp-email-service

# Using docker-compose
docker-compose up -d
```

### API Documentation & Interfaces

- **Swagger UI**: `http://localhost:1234/docs` - Interactive API documentation
- **ReDoc**: `http://localhost:1234/redoc` - Alternative API documentation
- **Web Interface**: `http://localhost:1234` - Main user interface
- **Admin Dashboard**: `http://localhost:1234/admin` - Configuration management
- **Logs Viewer**: `http://localhost:1234/static/logs` - Real-time log viewer
- **Test Endpoint**: `http://localhost:1234/test` - Cloudflare KV connection test

## Architecture

### Service Layer Pattern

The application follows a clean service-oriented architecture with clear separation of concerns:

```
app/
├── main.py              # FastAPI app initialization, lifespan management, CORS
├── config.py            # Settings (Pydantic Settings), domain configuration
├── models.py            # Pydantic models (Email, Mail, Code, API responses)
├── routers/
│   ├── email.py         # Email/mail endpoints (generate, fetch, codes, wait)
│   ├── system.py        # System endpoints (domains, health, test)
│   ├── admin.py         # Admin authentication and configuration management
│   └── pattern.py       # Pattern management API (admin-only)
├── services/
│   ├── email_service.py        # Email generation, validation, token creation
│   ├── mail_service.py         # Mail fetching (multi-source: KV or external API)
│   ├── kv_mail_service.py      # Cloudflare Workers KV client
│   ├── code_service.py         # Verification code extraction (regex + LLM)
│   ├── pattern_service.py      # Pattern learning and management
│   ├── pattern_code_service.py # Pattern-based code extraction
│   ├── llm_code_service.py     # LLM-based code extraction (OpenAI-compatible)
│   ├── maileroo_service.py     # Maileroo email sending integration
│   ├── storage_service.py      # In-memory storage with expiration cleanup
│   ├── cache_service.py        # Caching service
│   ├── cloudflare_helper.py    # Cloudflare API helper utilities
│   ├── html_sanitizer.py       # HTML content sanitization
│   ├── text_to_html_service.py # Plain text to HTML conversion
│   ├── auth_service.py         # Authentication utilities
│   ├── log_service.py          # Logging service
│   └── env_service.py          # Environment variable management
└── middleware/
    └── logging_middleware.py   # HTTP request/response logging

static/
├── index.html           # Main web interface
├── admin/               # Admin dashboard UI
└── logs/                # Logs viewer UI

workers/
├── email-handler.js     # Cloudflare Email Worker script
└── wrangler.toml        # Worker configuration

docs/
├── EMAIL_WORKERS_SETUP.md   # Complete Cloudflare setup guide
├── CUSTOM_DOMAINS.md        # Custom domain configuration
└── API.md                   # API documentation
```

### Key Design Patterns

**Singleton Services**: All services are instantiated as singletons at module level (`email_service`, `mail_service`, etc.) to ensure shared state and easy imports.

**In-Memory Storage**: `storage_service` maintains:
- `emails: Dict[token, Email]` - Email objects indexed by token
- `mails: Dict[email_token, List[Mail]]` - Mail lists per email
- `email_by_address: Dict[address, token]` - Address-to-token lookup

Automatic deduplication happens in `save_mails()` using mail IDs.

**Mail ID Generation**: Uses MD5 hash of `(to, from, subject, timestamp_to_seconds, content_preview)` to create stable IDs that prevent duplicate display even when auto-refreshing. Time is truncated to seconds to avoid microsecond differences.

**Background Tasks**: `lifespan` context manager in `app.main` starts an asyncio cleanup task that runs every 5 minutes to remove expired emails.

### Email Content Extraction

`mail_service.py` handles multiple API response formats:
- Tries multiple field names: `content`, `body`, `text`, `message`
- Falls back to HTML extraction if plain text is empty
- Removes script/style tags and HTML entities from HTML content
- Extracts verification codes from both plain text and HTML

### Verification Code Detection

**Triple Extraction Strategy** (`code_service.py`):

The service supports three extraction modes with cascading fallback:

1. **Pattern-based Extraction** (`pattern_code_service.py`):
   - Uses learned patterns from admin training (stored in `data/patterns.json`)
   - Matches context keywords before/after the code
   - Confidence scoring based on pattern success rate
   - Best for: Emails from known senders with consistent formats
   - Falls through if no patterns match

2. **LLM-based Extraction** (default, `USE_LLM_EXTRACTION=true`):
   - Uses OpenAI-compatible API (`llm_code_service.py`) to intelligently extract verification codes
   - Supports custom API endpoints (default: Longcat API)
   - Model: configurable via `OPENAI_MODEL` (default: "LongCat-Flash-Chat")
   - Higher accuracy for complex email formats and multiple code patterns
   - Falls back to regex if LLM extraction fails

3. **Regex-based Extraction** (`USE_LLM_EXTRACTION=false` or fallback):
   - Multiple regex patterns with confidence scoring:
     - Numeric codes (4, 6, 8 digits): confidence 0.8-0.9
     - Alphanumeric (6-10 chars): confidence 0.75
     - Context keywords ("code:", "驗證碼:", "OTP:"): confidence 0.95
     - URL parameters (`?code=`, `?token=`): confidence 0.85
   - Codes are sorted by confidence score descending
   - Lightweight, no external API dependency

**Configuration**:
```env
USE_LLM_EXTRACTION=true
OPENAI_API_KEY=your_api_key_here
OPENAI_API_BASE=https://api.longcat.chat/openai/v1
OPENAI_MODEL=LongCat-Flash-Chat
```

### Pattern Learning System ⭐️ (New)

**Interactive Learning** (`pattern_service.py`):

Admins can train the system to recognize verification codes from specific email formats by highlighting examples. The system learns contextual patterns and improves accuracy over time.

**How it works**:
1. Admin receives an email with verification code
2. In admin dashboard, paste email content and highlight the code
3. System extracts context (30 chars before/after) and keywords
4. Pattern is saved to `data/patterns.json` with:
   - Keywords before code (e.g., "驗證碼:", "OTP:", "code is")
   - Keywords after code (e.g., "有效期", "expires")
   - Code type (numeric/alphanumeric/token)
   - Code length and regex pattern
   - Example code for reference
5. Future emails matching this pattern get higher confidence scores

**Pattern Management** (`app/routers/pattern.py`):
- Patterns persist across restarts (file-based storage)
- Track usage count and success rate for each pattern
- Delete underperforming patterns
- Export/import patterns for sharing across instances

**Advantages**:
- ✅ Learn once, use forever
- ✅ No LLM API costs for learned patterns
- ✅ Higher confidence for known senders
- ✅ Automatic pattern ranking by success rate

### Multi-Source Mail Fetching with Smart Routing ⚡️

**Mail Service Architecture**: `mail_service.py` supports intelligent domain-based routing between multiple mail sources:

1. **Cloudflare Workers KV** (self-hosted, for custom domains):
   - Fetches emails from Workers KV storage
   - Populated by Email Worker (JavaScript) running on Cloudflare
   - Real-time email reception via Cloudflare Email Routing
   - Best for: Custom domains (e.g., `@leungchushing.best`)

2. **External API** (-compatible, for builtin domains):
   - Fetches from `https://mail.chatgpt.org.uk/api/get-emails?email={address}`
   - Returns JSON with `emails` array containing `from`, `subject`, `content`/`body`, `html`, `date`
   - Uses same API as  (proven to receive verification codes)
   - Best for: Builtin domains (e.g., `@chatgptuk.pp.ua`, `@gravityengine.cc`)

**Smart Routing Logic** in `mail_service.py`:
```python
async def fetch_mails(self, email: str) -> List[Mail]:
    # Intelligent domain-based routing
    from app.config import should_use_cloudflare_kv

    use_kv = should_use_cloudflare_kv(email)

    if use_kv:
        # Custom domains → Cloudflare KV
        return await self._fetch_from_cloudflare_kv(email)
    else:
        # Builtin domains → External API (mail.chatgpt.org.uk)
        return await self._fetch_from_external_api(email)
```

**Routing Decision Rules** (`app/config.py:should_use_cloudflare_kv()`):
1. If `USE_CLOUDFLARE_KV=false` → All domains use External API
2. If `USE_CLOUDFLARE_KV=true` and `CF_KV_DOMAINS` not set → All domains use KV (backward compatible)
3. If `USE_CLOUDFLARE_KV=true` and `CF_KV_DOMAINS=['leungchushing.best']` → Smart routing:
   - `test@leungchushing.best` → Cloudflare KV
   - `test@chatgptuk.pp.ua` → External API

**`CF_KV_DOMAINS` Configuration Details** (⚠️ New):

This is a critical configuration for hybrid mode operation:

- **Format**: JSON array string, e.g., `'["domain1.com", "domain2.com"]'`
- **Location**: Configurable via `.env` file or admin interface (`static/admin.html:838-850`)
- **Function**: `app/config.py:182-231` - `get_kv_domains()` and `should_use_cloudflare_kv()`
- **Behavior**:
  - **Empty/Not Set**: All domains use KV (backward compatible mode)
  - **Specified**: Only listed domains use KV, others use External API
- **Use Case**: Separate custom domains (with real email via Email Worker) from builtin domains (using proven External API)
- **Admin UI**: ⭐️ New field added in this update with智能路由 badge and detailed hints

**Hybrid Mode Configuration** (Recommended):
```env
USE_CLOUDFLARE_KV=true
CF_KV_DOMAINS='["leungchushing.best"]'  # Only custom domains use KV
ENABLE_CUSTOM_DOMAINS=true
ENABLE_BUILTIN_DOMAINS=true  # Builtin domains use External API
```

**Benefits of Smart Routing**:
- ✅ Custom domains receive real emails via your Email Worker
- ✅ Builtin domains receive verification codes via proven External API (-compatible)
- ✅ No need to configure Email Routing for 20 builtin domains
- ✅ Solves the "can't receive verification code" issue for builtin domains

**Long Polling**: `wait_for_new_mail()` polls the active mail source (determined by smart routing) every 5 seconds (configurable via `MAIL_CHECK_INTERVAL`) for up to 120 seconds max.

**Debug Logging**: Enable `DEBUG_EMAIL_FETCH=true` to see routing decisions:
```
[Mail Service] Domain: leungchushing.best → Source: Cloudflare KV
[Mail Service] Domain: chatgptuk.pp.ua → Source: External API (mail.chatgpt.org.uk)
```

### Cloudflare Email Workers Integration

**Complete Architecture Flow**:
```
User sends email → Cloudflare Email Routing (MX records)
                 → Email Worker (JavaScript on Cloudflare)
                 → Workers KV Storage (key: mail:{email}:{timestamp})
                 → FastAPI reads via KV API (kv_mail_service.py)
                 → User receives via REST API
```

**Email Worker** (`workers/email-handler.js`):
- Intercepts emails via Cloudflare Email Routing
- Parses email content (text and HTML)
- Generates stable mail IDs
- Stores to Workers KV with 1-hour TTL
- Maintains per-email index for efficient querying

**KV Client** (`app/services/kv_mail_service.py`):
- Cloudflare API integration for KV reads
- Supports both index-based and prefix-based mail fetching
- Handles pagination and filtering
- Connection testing and statistics

**Configuration Requirements**:
```env
USE_CLOUDFLARE_KV=true
CF_ACCOUNT_ID=your_account_id
CF_KV_NAMESPACE_ID=your_namespace_id
CF_API_TOKEN=your_api_token
```

**Deployment**: See `docs/EMAIL_WORKERS_SETUP.md` for complete setup guide including:
- Cloudflare DNS and Email Routing configuration
- Workers KV namespace creation
- Email Worker deployment with Wrangler CLI
- API token creation with correct permissions

## Configuration

Settings are loaded via Pydantic Settings from `.env` file or environment variables:

```python
# Server Configuration
PORT = 1234                         # Server port (default: 1234)
HOST = "0.0.0.0"                    # Server host
RELOAD = true                       # Auto-reload on code changes

# Email Service Configuration
EMAIL_TTL = 3600                    # Email expiration (seconds)
MAIL_CHECK_INTERVAL = 5             # Polling interval (seconds)
MAX_MAILS_PER_EMAIL = 50            # Storage limit per email

# Mail Source Configuration (Smart Routing)
USE_CLOUDFLARE_KV = false           # Enable Cloudflare Workers KV
CF_KV_DOMAINS = '["example.com"]'   # Domains using KV (smart routing), empty = all domains use KV
CF_ACCOUNT_ID = ""                  # Cloudflare Account ID
CF_KV_NAMESPACE_ID = ""             # Workers KV Namespace ID
CF_API_TOKEN = ""                   # Cloudflare API Token

# Custom Domains
ENABLE_CUSTOM_DOMAINS = false       # Enable custom domain support
CUSTOM_DOMAINS = '["example.com"]'  # JSON array of custom domains
DEFAULT_DOMAINS = '["example.com"]' # Preferred domain (70% selection chance)
ENABLE_BUILTIN_DOMAINS = true       # Include 20 built-in domains

# LLM Code Extraction
USE_LLM_EXTRACTION = true           # Enable LLM-based code extraction
OPENAI_API_KEY = ""                 # OpenAI-compatible API key
OPENAI_API_BASE = "https://api.longcat.chat/openai/v1"  # API endpoint
OPENAI_MODEL = "LongCat-Flash-Chat" # Model name

# Maileroo Email Sending
MAILEROO_API_URL = "https://smtp.maileroo.com/api/v2/emails"
MAILEROO_API_KEY = ""               # Maileroo API key

# Admin Authentication
ADMIN_USERNAME = "admin"            # Admin username
ADMIN_PASSWORD = "admin123"         # Admin password (change in production!)
ADMIN_SECRET_KEY = "your-secret-key-here"  # JWT secret key
JWT_ALGORITHM = "HS256"             # JWT algorithm
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

# Logging
ENABLE_FILE_LOGGING = true          # Enable file logging
LOG_FILE_PATH = "logs"              # Log directory
LOG_RETENTION_DAYS = 7              # Log retention period
LOG_MAX_FILE_SIZE_MB = 10           # Max log file size

# CORS
CORS_ORIGINS = ["*"]                # Allowed origins (supports JSON array or CSV)
```

### Domain Configuration

**Domain Merging Strategy** (`config.py`):
1. If custom domains enabled → add custom domains
2. If builtin domains enabled → add 20 built-in domains
3. Deduplicate and preserve order (custom first)

**Domain Selection Logic** (`email_service.py`):
- If `DEFAULT_DOMAINS` configured: 70% chance for default, 30% for others
- Otherwise: equal probability for all domains

**Validation**: Domain must be in active domain list (check via `/api/domains`)

### Admin Dashboard & Management

**Admin Interface** (`/admin`):
- Protected by JWT authentication
- Runtime configuration management (hot-reload vs restart required)
- System monitoring and statistics
- Log viewer with real-time updates
- **Cloudflare Helper Features** (⭐️ New):
  - **自動檢測 (Auto-Detect)** - Automatically detects Cloudflare credentials from local wrangler configuration
  - **配置向導 (Configuration Wizard)** - Step-by-step guide for Cloudflare setup with direct links and field highlighting
  - **測試連接 (Test Connection)** - Validates KV connection, permissions, and namespace access with detailed diagnostics
  - **智能路由配置 (Smart Routing Configuration)** - `CF_KV_DOMAINS` field for hybrid mode (⚠️ UI field added: `static/admin.html:838-850`)

**Runtime Configuration Feedback**:
- Configuration fields are marked as「即時生效」(Hot-Reload) or「需重啟」(Needs Restart)
- Simplified Chinese UI with technical hints and badge indicators
- Admin/logs UI includes zh-CN comments for better user experience

**Hidden UI Elements** (for UX simplification):

The following configuration fields are hidden from the admin interface to reduce complexity:

1. **`USE_LLM_EXTRACTION` checkbox** (`static/admin.html:903-909`)
   - Reason: LLM verification code extraction is enabled by default
   - User benefit: Simplifies interface by removing unnecessary toggle
   - Configuration method: Set via `.env` file (`USE_LLM_EXTRACTION=true/false`)

2. **`ADMIN_SECRET_KEY` field** (`static/admin.html:1001-1005`)
   - Reason: Security consideration - JWT secret should not be modifiable via web interface
   - User benefit: Prevents accidental or malicious secret key changes
   - Configuration method: Only configurable via environment variable (`ADMIN_SECRET_KEY=...`)

**Admin API Endpoints**:
- `POST /api/admin/login` - Authenticate with username/password
- `GET /api/admin/config` - Get current configuration
- `PUT /api/admin/config` - Update configuration (supports hot-reload)
- `GET /api/admin/stats` - Get system statistics
- `POST /admin/cloudflare/auto-detect` - Auto-detect Cloudflare credentials (⭐️ New)
- `GET /admin/cloudflare/wizard` - Get configuration wizard steps (⭐️ New)
- `POST /admin/cloudflare/test-connection` - Test KV connection (⭐️ New)

**Configuration Hot-Reload**:
Some settings can be updated without restarting the service:
- `MAIL_CHECK_INTERVAL` - Polling interval
- `MAX_MAILS_PER_EMAIL` - Storage limits
- `CF_KV_DOMAINS` - Smart routing configuration (⚠️ New)
- Cloudflare credentials (`CF_ACCOUNT_ID`, `CF_KV_NAMESPACE_ID`, `CF_API_TOKEN`)
- Domain settings (`ENABLE_CUSTOM_DOMAINS`, `CUSTOM_DOMAINS`, `DEFAULT_DOMAINS`, `ENABLE_BUILTIN_DOMAINS`)
- LLM settings (`OPENAI_API_KEY`, `OPENAI_API_BASE`, `OPENAI_MODEL`)
- Other settings require service restart (indicated in admin UI)

**Access**:
```bash
# Access admin dashboard
open http://localhost:1234/admin

# Login via API
curl -X POST http://localhost:1234/api/admin/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

### API Endpoints

**Email Management**:
- `POST /api/email/generate` - Generate temporary email
- `GET /api/email/{token}/mails` - Fetch mail list
- `GET /api/email/{token}/mails/{mail_id}` - Get mail details
- `GET /api/email/{token}/codes` - Extract verification codes
- `GET /api/email/{token}/wait` - Wait for new mail (long polling)
- `DELETE /api/email/{token}` - Delete email

**Admin Authentication**:
- `POST /api/admin/login` - Authenticate with username/password
- `GET /api/admin/config` - Get current configuration
- `PUT /api/admin/config` - Update configuration (supports hot-reload)
- `GET /api/admin/stats` - Get system statistics

**Pattern Management** (Admin-only, ⭐️ New):
- `POST /api/patterns/learn` - Learn new pattern from highlighted code
- `GET /api/patterns` - List all learned patterns with usage stats
- `DELETE /api/patterns/{pattern_id}` - Delete specific pattern
- `GET /api/patterns/stats` - Get pattern usage statistics

**System**:
- `GET /api/domains` - Get available domains with configuration info
- `GET /api/health` - Health check with uptime and active email count
- `GET /test` - Test Cloudflare KV connection, returns stats if enabled

## Frontend

**Main Interface** (`static/index.html`):
- Flat Design style (minimal, bold colors, sans-serif fonts)
- Auto-refresh toggle (polls every 10 seconds when enabled)
- Client-side deduplication using Set to prevent duplicate rendering
- Real-time countdown for email expiration
- Copy to clipboard with HTML entity handling
- Conditional forward button (hidden when using Cloudflare KV)
- Real-time API call monitoring with terminal-style logging

**Admin Dashboard** (`static/admin/`):
- Secure login with JWT authentication
- Runtime configuration editor with validation
- System statistics and monitoring
- Hot-reload indicators (shows which settings need restart)
- Simplified Chinese UI with technical hints

**Logs Viewer** (`static/logs/`):
- Real-time log streaming
- Filter by log level (INFO, WARNING, ERROR)
- Date-based log file selection
- Automatic refresh capabilities

## Important Behaviors

**Storage is ephemeral**: All data is lost on restart. No persistence layer.

**Expiration**: Emails expire after 1 hour. Cleanup runs every 5 minutes in background.

**Deduplication happens at three levels**:
1. Mail ID generation (stable hash based on content)
2. Backend `save_mails()` (checks existing IDs before adding)
3. Frontend rendering (filters duplicates via Set)

**CORS** (Cross-Origin Resource Sharing): Supports multiple configuration formats for deployment flexibility:
- **JSON array**: `CORS_ORIGINS='["http://example.com", "http://localhost:3000"]'`
- **Wildcard**: `CORS_ORIGINS="*"` or `CORS_ORIGINS=["*"]`
- **CSV string**: `CORS_ORIGINS="http://example.com, http://localhost:3000"`
- **Default**: Defaults to `["*"]` if parsing fails (allows all origins)
- **Configuration File**: `app/config.py` - `cors_origins` field accepts `Union[List[str], str]`
- **Parsing Function**: `app/config.py:156-179` - `get_cors_origins_list()` handles robust parsing:
  1. If already a list → convert elements to strings
  2. If string is `"*"` → return `["*"]`
  3. Try JSON parsing → return as list
  4. Fallback to CSV parsing → split by comma
  5. Final fallback → `["*"]`
- **Usage**: `app/main.py` uses `get_cors_origins_list()` to configure CORS middleware
- **Recent Enhancement** (commit `f4a20ac`): Made CORS origins robust to non-JSON env values to prevent startup crashes in production

**Error handling**: Most service methods catch exceptions and return empty results rather than propagating errors, to maintain service availability.

**Security**:
- Admin endpoints protected by JWT authentication
- Passwords hashed with bcrypt (12 rounds)
- Session tokens expire after 24 hours (configurable)
- Change default admin credentials in production (`ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_SECRET_KEY`)

**Logging**:
- File logging enabled by default to `logs/` directory
- Log files rotate when reaching 10MB (configurable)
- Logs retained for 7 days (configurable)
- Structured JSON logging for machine parsing

## Custom Domain Support

**Configuration Modes**:
1. **Builtin only** (default): Uses 20 pre-configured disposable domains
2. **Custom only**: `ENABLE_CUSTOM_DOMAINS=true`, `ENABLE_BUILTIN_DOMAINS=false`
3. **Hybrid**: Both custom and builtin domains active
4. **Priority mode**: Use `DEFAULT_DOMAINS` to set preferred domain with 70% selection weight

**Domain Validation**: API validates domain on email generation via `/api/email/generate?domain=example.com`

**Use Case**: Pair with Cloudflare Email Routing to receive real emails on your own domains

## Testing and Debugging

**Integration Testing**:
```bash
# Run full KV integration test suite
python test_kv_integration.py

# Tests: KV connection, mail fetching, API endpoint
```

**Manual API Testing**:
```bash
# 1. Generate email with specific domain
curl -X POST "http://localhost:1234/api/email/generate?domain=leungchushing.best"

# 2. Generate random email
curl -X POST http://localhost:1234/api/email/generate

# 3. Test KV connection (if enabled)
curl http://localhost:1234/test

# 4. Check available domains
curl http://localhost:1234/api/domains

# 5. Fetch mails for token
curl http://localhost:1234/api/email/{token}/mails

# 6. Extract verification codes
curl http://localhost:1234/api/email/{token}/codes
```

**Cloudflare Worker Debugging**:
```bash
# Stream Worker logs in real-time
cd workers
wrangler tail

# List KV keys
wrangler kv:key list --namespace-id=YOUR_NAMESPACE_ID

# Get KV value
wrangler kv:key get "mail:test@example.com:1234567890" --namespace-id=YOUR_NAMESPACE_ID
```

## Important Design Decisions

**Why multi-source mail fetching**: Allows gradual migration from external API to self-hosted Cloudflare solution without breaking existing deployments.

**Why Workers KV over direct SMTP**: KV provides simple HTTP API, no mail server management, automatic TTL, and integrates seamlessly with Cloudflare Email Routing.

**Why stable mail IDs**: Content-based hashing (MD5 of to+from+subject+content_preview) prevents duplicates during polling/auto-refresh, even with minor timestamp differences.

**Why singleton services**: Shared in-memory state (storage_service) requires single instance per process. Services are lightweight and stateless except for storage_service.

**Why 1-hour expiration**: Balances temporary email use case (verification codes expire quickly) with user convenience and memory constraints.

**Why pattern learning system** ⭐️:
- **Cost efficiency**: Learned patterns eliminate LLM API calls for common email formats
- **Accuracy**: Context-aware matching provides higher confidence than generic regex
- **Adaptability**: System improves over time as admins train on real-world examples
- **Persistence**: File-based storage (`data/patterns.json`) survives restarts without database
- **Privacy**: No email content sent to external APIs for learned patterns

## Recent Enhancements

### Frontend Improvements
- **Copy functionality fix**: Email addresses with special characters (like `@leungchushing.best`) now copy correctly without HTML entities
- **Conditional forward button**: Forward button is hidden when using Cloudflare KV (`useCloudflareKV=true`) since external URL is unavailable
- **Real-time API monitoring**: Terminal-style API call logging with request/response details and duration tracking

### API Enhancements
- **useCloudflareKV field**: Added to email generation response to indicate Cloudflare KV usage status
- **Enhanced query parameters**: Explicit Query() decorators with descriptions for better API documentation
- **Improved error handling**: Clear domain validation messages with available domain suggestions

### New Services
- **Pattern Learning System** ⭐️: Interactive pattern training system that learns from admin-highlighted examples
  - `pattern_service.py`: Pattern management with file-based persistence (`data/patterns.json`)
  - `pattern_code_service.py`: Pattern-based code extraction with confidence scoring
  - Admin UI for training, viewing, and managing patterns
  - Tracks usage count and success rate for each pattern
  - Reduces LLM API costs by learning common email formats
- **LLM Code Extraction**: Intelligent verification code extraction using OpenAI-compatible APIs with automatic fallback to regex
  - Separated into dedicated `llm_code_service.py` for better modularity
  - Supports custom API endpoints (default: Longcat API)
- **Maileroo Integration**: Email sending service integration (`app/services/maileroo_service.py`) for outbound email capabilities
- **Admin Authentication**: JWT-based authentication system with password hashing (bcrypt) for secure admin access
- **File Logging**: Structured logging to files with rotation, retention policies, and web-based viewer
- **Helper Services**:
  - `cache_service.py`: Caching utilities
  - `cloudflare_helper.py`: Cloudflare API helper functions
  - `html_sanitizer.py`: HTML content cleaning
  - `text_to_html_service.py`: Plain text to HTML conversion

### Testing Infrastructure
- **pytest Test Suite**: Located in `tests/` directory
  - `test_mail_service_external_parsing.py`: External mail API parsing tests
  - `test_maileroo_integration.py`: Maileroo service integration tests
- **Integration Tests**: Standalone scripts for end-to-end testing
  - `test_kv_integration.py`: Cloudflare KV integration validation
  - `test_custom_domains.py`: Custom domain configuration testing
  - `test_email_api_direct.py`: Direct API connection testing (diagnose mail fetching issues)

### Email Receiving Bug Fixes & Enhancements (2025-01-14)

**Problem**: External mail API fetching not working correctly despite using same endpoint as reference implementation ().

**Root Cause Analysis**:
1.  compatibility mode had logic bugs preventing fallback
2. Missing timeout and retry mechanisms
3. Lack of diagnostic tools for end-to-end testing

#### Phase 1 Fixes (Initial Debugging):
1. **`app/services/mail_service.py:73-123`**: Fixed  compatibility mode
   - Only return early when mails are found
   - Allow fallback to generic parsing

2. **Enhanced debug logging**:
   - Full API response structure logging
   - Complete error traceback in debug mode

3. **`test_email_api_direct.py`**: Diagnostic tool for API testing

#### Phase 2 Enhancements ( Pure Implementation):
**Key Implementation**: Created `_fetch_reliable()` method that 100% mirrors 's Deno/Go implementation

**Changes**:
1. **`app/services/mail_service.py:44-146`**: New  Pure mode
   - Complete clone of  logic (Deno/Go versions)
   - HTTP timeout: 30s (vs 's 10s for better stability)
   - Automatic retry: 3 attempts with 2s delay
   - Direct `data.emails` parsing without complex fallbacks
   - Usage: `EMAIL_COMPAT_MODE=reliable`

2. **`app/config.py:19-23`**: New configuration options
   ```python
   email_compat_mode: "enhanced" | "reliable" | None
   email_request_timeout: 30.0  # seconds
   email_retry_times: 3          # attempts
   ```

3. **`test_email_flow_e2e.py`**: End-to-end test script
   - Mimics 's polling logic
   - 60-second timeout with 5-second intervals
   - Progress reporting every 10 seconds
   - Interactive email sending prompts
   - Usage: `python test_email_flow_e2e.py`

4. **`.env.example:16-31`**: Updated configuration documentation
   - Three modes: default, enhanced, reliable
   - HTTP timeout and retry settings
   - Clear usage instructions

**Configuration Modes**:
```env
# Mode 1: Generic (default)
# EMAIL_COMPAT_MODE not set
# Uses multi-layer parsing with all fallbacks

# Mode 2: Enhanced 
EMAIL_COMPAT_MODE=enhanced
# Strict parsing with generic fallback

# Mode 3: Pure  (Recommended for debugging)
EMAIL_COMPAT_MODE=reliable
DEBUG_EMAIL_FETCH=true
EMAIL_REQUEST_TIMEOUT=30.0
EMAIL_RETRY_TIMES=3
# 100% identical to  implementation
```

**Testing**:
```bash
# Test 1: Direct API connection
python test_email_api_direct.py

# Test 2: End-to-end flow (with polling)
python test_email_flow_e2e.py

# Test 3: Regression tests
python -m pytest tests/test_mail_service_external_parsing.py -v

# Test 4: Test with custom email
python test_email_api_direct.py your-email@example.com
```

**Performance & Reliability**:
- ✅ 30-second timeout (3x 's 10s)
- ✅ 3 automatic retries with exponential backoff
- ✅ Detailed logging at each retry attempt
- ✅ Same domains as  (20 built-in domains)
- ✅ Identical API request format

**Reference**:
-  Deno: `deno/zai/zai_register.ts` - `fetchVerificationEmail()`
-  Go: `register/accounts.go` - `waitForVerificationEmail()`
- Analysis via DeepWiki MCP
