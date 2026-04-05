---
applyTo: '**'
---
# Agent Instructions

This file provides guidance to the AI Agent when working with code in this repository.

## Quick start

```bash
# Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_lg

# Run the REST API (port 8000)
uvicorn src.api:api --host 0.0.0.0 --port 8000 --reload

# Run the MCP server (port 8001)
uvicorn mcp_main:app --host 0.0.0.0 --port 8001 --reload

# Run unit tests (no external services needed)
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ --cov=src --cov-report=html

# Run integration tests
pytest tests/integration/ -v

# Lint and format
ruff check --fix src tests mcp_server
black src tests mcp_server
isort src tests mcp_server
```

## Architecture

**Tech stack:**
- FastAPI with uvicorn, Python 3.13, async/await
- Microsoft Presidio (AnalyzerEngine, AnonymizerEngine, PatternRecognizer)
- spaCy NLP models per language (en_core_web_lg required; others optional)
- langdetect for automatic language detection
- Anthropic Claude API for summarization (extractive fallback if no key)
- MCP (Model Context Protocol) via FastMCP — SSE transport (port 8001) + stdio for Claude Desktop
- slowapi for burst rate limiting; in-memory or Redis-backed quota tracking
- Azure Log Analytics HTTP Data Collector API with HMAC-SHA256 signing

**Two transport layers, one business logic layer:**
```
Browser / REST clients          AI Agents (Claude, Trimble tools)
        │                                 │
        │ REST :8000                      │ MCP SSE :8001 / stdio
        ▼                                 ▼
  src/api.py                     mcp_server/server.py
        │                                 │
        └──────────── shared ─────────────┘
                   src/redaction/
                   src/summarization/
                   src/redaction/custom_patterns.py
```

**Target request flow:**
```
Router → Service → (external call if needed)
               └→ logger.info(..., extra={trace fields})
                       └→ AzureLogAnalyticsHandler → Log Analytics
```
Routers handle HTTP only. Services contain business logic. No business logic in routers.

## File organisation

```
src/
├── api.py                    # FastAPI app init + router registration
├── models.py                 # All Pydantic DTOs — new models go here only
├── constants.py              # Env var keys + hardcoded constants
├── errors/
│   ├── exceptions.py         # Domain exceptions
│   └── exception_handlers.py # Global HTTP error handlers
├── routers/                  # HTTP only — no business logic
│   ├── health.py
│   ├── redaction.py
│   ├── summarization.py
│   └── patterns.py
├── redaction/
│   ├── extractor.py          # File → plain text
│   ├── redactor.py           # Presidio engine (lazy-loaded singleton)
│   └── custom_patterns.py    # Per-business-unit pattern CRUD
├── summarization/
│   └── summarizer.py
└── util/
    ├── auth.py               # verify_api_key dependency
    ├── logging_config.py     # Structured logging + Azure handler
    ├── rate_limit.py         # slowapi limiter + key identification
    └── quota.py              # Daily LLM quota tracker

mcp_server/
├── app.py                    # Shared FastMCP instance
├── server.py                 # ASGI app (SSE + auth + /health)
├── middleware.py             # MCP_API_KEY auth
└── tools/
    ├── redact.py             # MCP tool wrappers → src/redaction/
    ├── summarize.py          # MCP tool wrappers → src/summarization/
    └── patterns.py           # MCP tool wrappers → src/redaction/custom_patterns.py
```

## Conventions

**Naming:**
- Python files: `snake_case`
- Classes: `PascalCase` (models use Pydantic BaseModel)
- Functions: `snake_case`
- API router prefixes: lowercase (e.g., `/redact`, `/patterns`)
- Environment variables: `UPPERCASE_WITH_UNDERSCORES`
- Custom PII entity types: `UPPERCASE_WITH_UNDERSCORES` (e.g., `CONSTR_BID_NUMBER`)

**Models:**
All Pydantic request/response DTOs live in `src/models.py`. Never define models inline in routers.

**Presidio engine:**
The Presidio `AnalyzerEngine` and `AnonymizerEngine` are lazy-loaded singletons in `src/redaction/redactor.py`. Call `mark_analyzer_dirty()` whenever custom patterns are added or deleted — this resets the singleton so it rebuilds with new patterns on the next redact call.

**Custom patterns:**
Built-in patterns live in `BUILTIN_PATTERNS` in `src/redaction/custom_patterns.py` (read-only).
User-defined patterns are persisted to `data/custom_patterns.json`. Never commit this file.

**MCP tools:**
Each tool module in `mcp_server/tools/` imports the shared `mcp` instance from `mcp_server/app.py` and registers tools via `@mcp.tool()` decorator (side-effect at import time). `mcp_server/server.py` imports all tool modules to trigger registration, then calls `mcp.sse_app()`.

**Rate limiting:**
- `LIMIT_GENERAL`, `LIMIT_PROCESS`, `LIMIT_SUMMARIZE` are plain strings defined in `src/util/rate_limit.py`
- slowapi decorators require `request: Request` as a parameter in the route function
- Daily LLM quota is enforced separately in `src/util/quota.py` — check before calling Claude, record after
- Per-team limits are configured in `quota_config.json` at project root

**Logging:**
Use `logging.getLogger(__name__)` everywhere. Never use `print()`. Pass trace fields via `extra={}` dict. Use `doc_filename` not `filename` in `extra` — `filename` is a reserved `LogRecord` attribute and will raise `KeyError`.

**Error handling:**
Domain exceptions are defined in `src/errors/exceptions.py` and converted to HTTP responses via global handlers in `src/errors/exception_handlers.py`. Routers must not use `try/except` for domain errors — let them bubble up.

**Import statements:**
All imports at the top of the file in PEP 8 order: stdlib → third-party → local. Deferred imports only for optional dependencies (e.g., `presidio_analyzer`, `anthropic`, `langdetect`) that should not be loaded at startup.

**Auth:**
`verify_api_key` FastAPI dependency injected on all REST routers. Auth disabled when `API_KEY` env var is not set (dev mode). MCP server uses `MCPAPIKeyMiddleware` checking `MCP_API_KEY`.

## Libraries

**Actively used:**
- `fastapi`, `uvicorn[standard]`, `pydantic`, `python-multipart`, `python-dotenv`
- `presidio-analyzer`, `presidio-anonymizer`, `spacy`
- `langdetect`
- `pdfplumber`, `python-docx`
- `anthropic`
- `mcp[cli]`
- `slowapi`
- `httpx`
- `pytest`, `pytest-cov`, `pytest-mock`, `pytest-asyncio`
- `ruff`, `black`, `isort`

**Rules:**
- All dependencies pinned to specific versions in `requirements.txt`
- Never use unbounded version specifiers (e.g., `httpx>=0.20`)

## Testing

Framework: pytest with pytest-cov, pytest-mock, pytest-asyncio.

**Key fixtures (`tests/utils/fixtures.py`):**
- `api_client` — `TestClient` with `verify_api_key` overridden
- `auth_headers` — test API key header
- Mock data in `tests/utils/mock_data.py`

**Patterns:**
- Unit tests: mock Presidio, Anthropic, file I/O — no real NLP models needed
- Integration tests: use `TestClient` against the real FastAPI app
- AAA pattern: Arrange / Act / Assert
- Test naming: `test_<method>_<scenario>_<expected_outcome>`

**Required before shipping:**
- Unit tests written for new routers/services
- All tests pass: `pytest tests/unit/`
- No lint violations: `ruff check src` and `black --check src`

## Security

- All secrets via environment variables loaded with `python-dotenv`
- Never hardcode credentials or API keys
- `.env` and `data/custom_patterns.json` are git-ignored
- Input validated with Pydantic `Field` constraints at router boundaries
- Custom regex patterns validated with `re.compile()` before persistence

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | No | Claude API key — omit for extractive fallback |
| `API_KEY` | No | REST API key (`X-API-Key` header). Unset = auth disabled |
| `API_KEY_HEADER` | No | Header name override (default: `X-API-Key`) |
| `MCP_API_KEY` | No | MCP server key. Unset = auth disabled |
| `REDIS_URL` | No | Redis for distributed rate limiting. Unset = in-memory |
| `AZURE_LOG_WORKSPACE_ID` | No | Log Analytics workspace ID |
| `AZURE_LOG_WORKSPACE_KEY` | No | Log Analytics shared key (base64) |
| `AZURE_LOG_TYPE` | No | Custom table name (default: `PIIRedactionTrace`) |

## Definition of done

A feature is complete only when:
- [ ] Code follows naming, file organisation, and async conventions above
- [ ] Unit tests written and passing: `pytest tests/unit/ -v`
- [ ] `ruff check --fix` and `black` pass with no changes
- [ ] No hardcoded secrets, proper input validation at boundaries
- [ ] All tests pass: `pytest tests/`
