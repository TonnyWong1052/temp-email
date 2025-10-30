# Repository Guidelines

## Project Structure & Module Organization
- `app/` FastAPI 服務：路由、設定、服務、Middleware（啟動於 `app/main.py`）。
- `workers/` Cloudflare Email Worker（KV 儲存與部署配置在 `workers/wrangler.toml`）。
- `src/` TypeScript 公用服務/型別（編譯由 `tsc` 產出至 `dist/`）。
- `static/` Web UI 與 API 文件（`/docs`、`/redoc` 會引用此處中文頁面）。
- `data/` 範例資料；`logs/` 應用與錯誤日誌；根目錄包含 `Dockerfile`、`docker-compose.yml`、`pyproject.toml`、`requirements.txt`、`package.json`。

## Build, Test, and Development Commands
- Python 開發
  - 建置環境：`python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
  - 本地啟動：`python run.py`（或 `uvicorn app.main:app --reload --host 0.0.0.0 --port 1234`）
- Node/TS 工具
  - 安裝與編譯：`npm install && npm run build`（`tsc` 產出 `dist/`）
- Cloudflare Worker 部署
  - `cd workers && wrangler login && wrangler deploy`
- Docker（可選）：`docker-compose up -d`

## Coding Style & Naming Conventions
- Python：4 空格縮排；PEP 8；函式/變數 `snake_case`、類別 `PascalCase`、強制型別註解。
  - Lint/Format：`ruff check .`、`black .`（設定見 `pyproject.toml`，line-length=100）。
- TypeScript：2 空格縮排；變數/函式 `camelCase`、型別/類別 `PascalCase`；檔名示例：`storage.service.ts`。

## Testing Guidelines
- Python：使用 `pytest`/`pytest-asyncio`。建議建立 `tests/`，檔名 `test_*.py`，執行 `pytest -q`。
- Node：目前未配置測試框架；如需加入，建議 `vitest` 或 `jest`，檔名 `*.spec.ts`。

## Commit & Pull Request Guidelines
- Commit 採用 Conventional Commits：`feat: ...`、`fix: ...`、`docs: ...`、`chore: ...`。
  - 例：`feat: add Redis cache with TTL control`、`fix: handle KV fallback when missing namespace`。
- PR 要求：
  - 清晰描述變更與動機、影響範圍；附上啟動/測試步驟；涉及 UI/行為請附截圖或日誌。
  - 連結關聯議題；標明需環境變數（`.env.example` 已提供範例）。

## Security & Configuration Tips (Optional)
- 勿提交敏感資訊；使用 `.env`（鍵值見 `app/config.py` 與 `workers/wrangler.toml`）。
- 變更預設管理員密碼與 JWT 金鑰；高併發建議啟用 Redis（`ENABLE_REDIS` 相關設定）。
