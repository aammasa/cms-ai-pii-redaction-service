# redact — PII Redaction & Summarization Service

A self-contained service for extracting text from documents, detecting and redacting PII across multiple languages, summarizing the clean output, and exposing all capabilities to AI agents via MCP. All activity is traced to Azure Log Analytics Workspace.

---

## Project structure

```
├── src/
│   ├── api.py                    # FastAPI app initialisation + router registration
│   ├── models.py                 # All Pydantic request/response DTOs
│   ├── constants.py              # Env var keys + hardcoded constants
│   ├── errors/
│   │   ├── exceptions.py         # Domain exceptions
│   │   └── exception_handlers.py # Global HTTP error handlers
│   ├── routers/
│   │   ├── health.py             # GET /health, /entities, /languages
│   │   ├── redaction.py          # POST /redact, /process
│   │   ├── summarization.py      # POST /summarize (quota enforced)
│   │   └── patterns.py           # GET|POST /patterns, DELETE /patterns/{id}, POST /patterns/test
│   ├── redaction/
│   │   ├── extractor.py          # File → plain text
│   │   ├── redactor.py           # Presidio PII detection + redaction
│   │   └── custom_patterns.py    # Per-business-unit pattern CRUD + persistence
│   ├── summarization/
│   │   └── summarizer.py         # Claude-powered summarization
│   └── util/
│       ├── auth.py               # API key dependency
│       ├── logging_config.py     # Structured logging + Azure Log Analytics handler
│       ├── rate_limit.py         # slowapi limiter + per-key identification
│       └── quota.py              # Daily LLM quota tracker (in-memory / Redis)
│
├── mcp_server/                   # MCP server — AI agent access layer
│   ├── app.py                    # Shared FastMCP instance
│   ├── server.py                 # ASGI app factory (SSE + auth middleware + /health)
│   ├── middleware.py             # MCP_API_KEY auth middleware
│   └── tools/
│       ├── redact.py             # redact_text, list_entities, list_languages
│       ├── summarize.py          # summarize_text
│       └── patterns.py           # list/add/delete/test custom patterns
│
├── tests/
│   ├── conftest.py
│   ├── unit/                     # Mocked, no external services needed
│   ├── integration/              # Full app via TestClient
│   └── utils/                    # Shared fixtures + mock data
│
├── data/
│   └── custom_patterns.json      # Persisted user-defined patterns (auto-created)
│
├── quota_config.json             # Per-team rate limits and LLM quotas
├── index.html                    # Single-page UI (no build step)
├── main.py                       # REST entry point shim → src.api:api
├── mcp_main.py                   # MCP SSE entry point → mcp_server.server:app (port 8001)
├── mcp_stdio.py                  # MCP stdio entry point → for Claude Desktop
├── Dockerfile                    # Single image, two startup commands
├── docker-compose.yml            # REST + MCP as separate scalable services
├── requirements.txt
└── .env.example
```

---

## Quick start

### 1. Install dependencies

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_lg
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY and optionally Azure + auth credentials
```

### 3. Run the REST API

```bash
uvicorn src.api:api --host 0.0.0.0 --port 8000 --reload
```

### 4. Run the MCP server (separate process)

```bash
uvicorn mcp_main:app --host 0.0.0.0 --port 8001 --reload
```

### 5. Open the UI

```bash
open index.html
# or: python -m http.server 3000 then visit http://localhost:3000
```

> The UI expects the backend at `http://localhost:8000`.

### 6. Run both with Docker

```bash
docker compose up                        # start REST + MCP
docker compose up --scale mcp-server=3  # scale MCP independently
```

---

## Architecture

```
Browser (index.html)                   AI Agents / Claude Desktop
        │                                        │
        │  REST (port 8000)                      │  MCP stdio / SSE (port 8001)
        ▼                                        ▼
FastAPI  src/api.py                    MCP Server  mcp_server/server.py
        │                                        │
        ├── src/routers/               ├── mcp_server/tools/redact.py
        ├── src/redaction/             ├── mcp_server/tools/summarize.py
        ├── src/summarization/         └── mcp_server/tools/patterns.py
        └── src/util/                            │
            ├── rate_limit.py                    │
            ├── quota.py                         │
            └── logging_config.py               │
                │                               │
                └──────── shared ───────────────┘
                       src/redaction/
                       src/summarization/
                       src/redaction/custom_patterns.py
                               │
                       Azure Log Analytics
```

### Two transport layers, one business logic layer

| Transport | Entry point | Port | Used by |
|---|---|---|---|
| REST (HTTP) | `main.py` → `src.api:api` | 8000 | Browser UI, direct REST clients |
| MCP SSE | `mcp_main.py` → `mcp_server.server:app` | 8001 | Remote AI agents, Trimble-wide access |
| MCP stdio | `mcp_stdio.py` | — | Claude Desktop (local subprocess) |

Both MCP transports expose the same 9 tools backed by the same `src/` services.

### Request flow

```
Router / Tool → Service → (external call if needed)
    │                  └→ logger.info(..., extra={trace fields})
    │                          └→ AzureLogAnalyticsHandler → Log Analytics
    │
    ├── Rate limit check (slowapi — burst guard per API key)
    └── Quota check (quota.py — daily LLM calls per team)
```

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | No | Claude API key — omit to use extractive summarization fallback |
| `API_KEY` | No | REST API key — all requests must include it in `X-API-Key` header. Unset = auth disabled |
| `API_KEY_HEADER` | No | Header name for REST API key (default: `X-API-Key`) |
| `MCP_API_KEY` | No | MCP server key — agents must send `Authorization: Bearer <key>` or `X-MCP-Key: <key>`. Unset = auth disabled |
| `REDIS_URL` | No | Redis connection URL for distributed rate limiting across pods (e.g. `redis://localhost:6379/0`). Unset = in-memory |
| `AZURE_LOG_WORKSPACE_ID` | No | Log Analytics workspace ID — omit to log to stdout only |
| `AZURE_LOG_WORKSPACE_KEY` | No | Log Analytics primary/secondary shared key (base64) |
| `AZURE_LOG_TYPE` | No | Custom table name in Log Analytics (default: `PIIRedactionTrace`) |

---

## Rate Limiting & Quotas

The service enforces two independent limits to prevent abuse and control LLM costs.

### 1. Burst rate limits (slowapi)

Applied per API key (falls back to IP when auth is disabled). Each key gets its own counter bucket — teams don't share limits.

| Endpoint | Default limit |
|---|---|
| `POST /redact` | 60 requests / minute |
| `POST /process` | 30 requests / hour |
| `POST /summarize` | 10 requests / hour |

When exceeded, the response is `HTTP 429` with standard `X-RateLimit-*` headers.

### 2. Daily LLM quota (cost control)

Tracks Claude API calls per team per UTC day. Resets automatically at midnight — no cron job needed. Uses in-memory storage by default; set `REDIS_URL` for multi-pod deployments.

| Team | Summarize calls / day |
|---|---|
| Default (unlisted key) | 50 |
| Construction / Agriculture / Geospatial | 200 |
| HR / Legal | 100 |
| Admin | 1000 |

### Quota response headers

Every `/summarize` response includes:

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-Quota-Summarize-Limit: 50
X-Quota-Summarize-Used: 12
X-Quota-Summarize-Remaining: 38
X-Quota-Reset: 2026-04-06
```

### Configuring per-team limits (`quota_config.json`)

Edit `quota_config.json` at the project root. Changes take effect on server restart.

```json
{
  "default": {
    "requests_per_minute": 60,
    "process_per_hour": 30,
    "summarize_per_day": 50
  },
  "teams": {
    "their-api-key": {
      "name": "New Team",
      "requests_per_minute": 120,
      "process_per_hour": 60,
      "summarize_per_day": 200
    }
  }
}
```

### Production — Redis backend

```bash
# .env
REDIS_URL=redis://your-redis-host:6379/0
```

Rate limit counters are then shared across all pods — no per-pod drift.

### Testing rate limits

```bash
# Single call — inspect quota headers
curl -i -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"redacted_text": "A person works at a company.", "length": "short"}' \
  | grep -E "X-Quota|X-RateLimit|HTTP"

# Python test — 6 calls against a quota of 3 (set summarize_per_day: 3 in quota_config.json)
python3 - << 'EOF'
import httpx, time
for i in range(6):
    r = httpx.post("http://localhost:8000/summarize",
        json={"redacted_text": "Test text.", "length": "short"}, timeout=15)
    used = r.headers.get("X-Quota-Summarize-Used", "?")
    rem  = r.headers.get("X-Quota-Summarize-Remaining", "?")
    lim  = r.headers.get("X-Quota-Summarize-Limit", "?")
    print(f"Call {i+1}: HTTP {r.status_code} | quota {used}/{lim} | remaining {rem}")
    time.sleep(0.2)
EOF
```

Expected output:
```
Call 1: HTTP 200 | quota 1/3 | remaining 2
Call 2: HTTP 200 | quota 2/3 | remaining 1
Call 3: HTTP 200 | quota 3/3 | remaining 0
Call 4: HTTP 429 | quota 3/3 | remaining 0   ← blocked
Call 5: HTTP 429 | quota 3/3 | remaining 0
Call 6: HTTP 429 | quota 3/3 | remaining 0
```

---

## MCP Server

### Overview

The MCP server runs as a **separate process** on port 8001 and exposes PII redaction capabilities to AI agents via the Model Context Protocol. It shares all business logic with the REST API — only the transport layer differs.

### MCP tools

| Tool | Description |
|---|---|
| `redact_text` | Detect and redact PII from plain text (all operators, all languages) |
| `list_entities` | List all supported PII entity types including active custom patterns |
| `list_languages` | List supported languages and spaCy model install status |
| `summarize_text` | Summarize PII-free text via Claude (or extractive fallback) |
| `list_business_units` | List the four supported business units |
| `list_patterns` | List patterns filtered by business unit |
| `add_custom_pattern` | Create and persist a new custom PII pattern |
| `delete_custom_pattern` | Delete a user-defined pattern by ID |
| `test_regex_pattern` | Test regex(es) against sample text without persisting |

### Authentication

```
# SSE transport (remote agents)
Authorization: Bearer <MCP_API_KEY>
# or
X-MCP-Key: <MCP_API_KEY>
```

The `/health` endpoint on port 8001 is always public (no auth required).

### Claude Desktop setup

1. Open `~/Library/Application Support/Claude/claude_desktop_config.json`
2. Add:

```json
{
  "mcpServers": {
    "pii-redaction": {
      "command": "/path/to/project/.venv/bin/python3",
      "args": ["/path/to/project/mcp_stdio.py"]
    }
  }
}
```

3. Restart Claude Desktop — the 🔨 hammer icon will show all 9 tools under `pii-redaction`.

### Remote agent setup (SSE)

```json
{
  "mcpServers": {
    "pii-redaction": {
      "url": "http://mcp-server:8001/sse",
      "headers": {
        "Authorization": "Bearer your-mcp-secret-key"
      }
    }
  }
}
```

### Example agent prompts (Claude Desktop)

```
Using pii-redaction, redact then summarize:
"John Smith (EMP-10029) submitted bid BID-2024-008821 from john@trimble.com.
Contract CNT-2024-REF00812, SSN 123-45-6789."
```

```
Using pii-redaction, add a custom pattern for construction:
entity CONSTR_PROJECT_CODE, regex \bPROJ-[A-Z]{2}-\d{4}-\d{4}\b,
context "project code, proj id". Then redact: "Project PROJ-TX-2024-0091 assigned."
```

---

## Custom PII Patterns

Per-business-unit regex patterns extend the built-in Presidio recognizers. Patterns persist to `data/custom_patterns.json` and activate on the next redact call.

### Business units

| Unit | ID | Built-in entities |
|---|---|---|
| Construction | `construction` | `CONSTR_BID_NUMBER`, `CONSTR_PERMIT_NUMBER`, `CONSTR_SUBCONTRACTOR_ID`, `CONSTR_SITE_CODE` |
| Agriculture | `agriculture` | `AGRI_FARM_ID`, `AGRI_PARCEL_ID`, `AGRI_YIELD_RECORD` |
| Geospatial | `geospatial` | `GEO_SURVEY_LICENSE`, `GEO_CONTROL_POINT_ID` |
| HR / Legal | `hr_legal` | `HR_EMPLOYEE_ID`, `HR_COST_CODE`, `HR_CONTRACT_REF` |

### Admin UI

Click **Custom Patterns** (gear icon) in the top-right header of the UI:
- Browse built-in patterns per business unit
- Add custom patterns with regex, context keywords, and confidence score
- Test regex against sample text before saving
- Delete user-defined patterns

### API

```bash
# List all patterns for a unit
curl http://localhost:8000/patterns?unit=construction

# Add a custom pattern
curl -X POST http://localhost:8000/patterns \
  -H "Content-Type: application/json" \
  -d '{
    "entity_type": "CONSTR_PROJECT_CODE",
    "label": "Project Code",
    "unit": "construction",
    "patterns": ["\\bPROJ-[A-Z]{2}-\\d{4}-\\d{4}\\b"],
    "context": ["project code", "proj id"],
    "score": 0.85
  }'

# Test a regex
curl -X POST http://localhost:8000/patterns/test \
  -H "Content-Type: application/json" \
  -d '{"patterns": ["\\bPROJ-[A-Z]{2}-\\d{4}\\b"], "sample_text": "Project PROJ-TX-2024 approved"}'

# Delete a pattern
curl -X DELETE http://localhost:8000/patterns/{id}
```

---

## Tracing & Logging

Every API action emits a structured trace record via Python's standard `logging` module.

### Destinations

- **Stdout** — always active, human-readable. Captured by any container log driver.
- **Azure Log Analytics Workspace** — active when `AZURE_LOG_WORKSPACE_ID` and `AZURE_LOG_WORKSPACE_KEY` are set. Records land in `PIIRedactionTrace_CL`.

### Trace fields

| Field | Type | Description |
|---|---|---|
| `timestamp` | ISO 8601 | UTC time of the event |
| `level` | string | Log level (`INFO`, `WARNING`, `ERROR`) |
| `event_type` | string | `process` \| `redact` \| `summarize` |
| `client_ip` | string | Caller IP (respects `X-Forwarded-For`) |
| `session_id` | string | UUID grouping related events for one document |
| `filename` | string | Uploaded filename (`process` events only) |
| `file_type` | string | File extension (`pdf`, `txt`, etc.) |
| `detected_language` | string | ISO 639-1 code auto-detected by langdetect |
| `entity_counts` | object | `{"PERSON": 2, "EMAIL_ADDRESS": 1, ...}` |
| `pii_count` | int | Total PII spans found |
| `operator` | string | Redaction style used (`replace`, `mask`, etc.) |
| `text_length` | int | Character count of input text |
| `summarization_run` | bool | Whether Claude was called |
| `llm_model` | string | Model ID used for summarization |

### KQL queries

```kusto
// All PII processing events in the last 24 hours
PIIRedactionTrace_CL
| where TimeGenerated > ago(24h)
| where event_type_s == "process"
| project TimeGenerated, client_ip_s, filename_s, detected_language_s, pii_count_d

// Top PII types detected this week
PIIRedactionTrace_CL
| where TimeGenerated > ago(7d)
| mv-expand entity_counts_s
| summarize total = sum(todouble(entity_counts_s)) by tostring(entity_counts_s)
| order by total desc

// Summarize quota usage per team key
PIIRedactionTrace_CL
| where TimeGenerated > ago(1d)
| where event_type_s == "summarize"
| summarize calls = count() by client_ip_s
| order by calls desc
```

---

## API Reference

### `GET /health`
```json
{ "status": "ok" }
```

### `GET /entities`
Returns all supported PII entity types including active custom patterns.

### `GET /languages`
Returns supported languages and whether their spaCy NLP model is installed.

### `POST /process`
Upload a file, extract text, auto-detect language, and redact PII.

**Request** — `multipart/form-data`

| Field | Type | Description |
|---|---|---|
| `file` | file | `.txt`, `.pdf`, `.docx`, `.doc`, `.csv`, `.md` |
| `language` | string | ISO 639-1 code or `"auto"` (default) |
| `session_id` | string | Optional — groups trace events |

```bash
curl -X POST http://localhost:8000/process \
  -F "file=@document.pdf" -F "language=auto"
```

**Response**
```json
{
  "original_text": "My name is John Smith...",
  "redacted_text": "My name is <PERSON>...",
  "entities_found": [{"type": "PERSON", "start": 11, "end": 21, "score": 0.85, "original": "John Smith"}],
  "entity_counts": {"PERSON": 1},
  "detected_language": "en",
  "filename": "document.pdf",
  "file_type": "pdf",
  "session_id": "a1b2c3d4-..."
}
```

### `POST /redact`
Redact PII from raw text.

| Field | Type | Default | Description |
|---|---|---|---|
| `text` | string | required | Plain text to redact |
| `language` | string | `"auto"` | ISO 639-1 code or `"auto"` |
| `entities` | list | all | Entity IDs to detect |
| `operator` | string | `"replace"` | `replace` \| `redact` \| `mask` \| `hash` |
| `session_id` | string | — | Groups trace events |

```bash
curl -X POST http://localhost:8000/redact \
  -H "Content-Type: application/json" \
  -d '{"text": "Contact Sarah at sarah@example.com", "operator": "mask"}'
```

### `POST /summarize`
Summarize PII-free text via Claude. Subject to hourly burst limit and daily LLM quota.

| Field | Type | Default | Description |
|---|---|---|---|
| `redacted_text` | string | required | PII-free text |
| `length` | string | `"short"` | `short` \| `medium` \| `detailed` |
| `session_id` | string | — | Groups trace events |

Returns `HTTP 429` when daily quota is exceeded. Quota headers are included on every response.

### `GET /patterns`
List custom PII patterns. Filter with `?unit=construction`.

### `GET /patterns/units`
List the four business units.

### `POST /patterns`
Create a custom pattern.

| Field | Type | Description |
|---|---|---|
| `entity_type` | string | Uppercase ID e.g. `CONSTR_PROJECT_CODE` |
| `label` | string | Human-readable label |
| `unit` | string | `construction` \| `agriculture` \| `geospatial` \| `hr_legal` |
| `patterns` | list | Regex pattern strings |
| `context` | list | Context keywords (optional) |
| `score` | float | Confidence 0.0–1.0 (default 0.80) |

### `DELETE /patterns/{id}`
Delete a user-defined pattern. Returns 403 for built-in patterns.

### `POST /patterns/test`
Test regex patterns against sample text without persisting.

---

## Multi-language PII detection

Language is auto-detected via `langdetect`. The detected language drives spaCy NLP (names, locations, orgs). Country-specific IDs use regex and work regardless of which NLP model is installed.

| Region | Languages | NLP model |
|---|---|---|
| Default | English | `en_core_web_lg` ✓ |
| Europe | German, French, Spanish, Dutch, Italian, Swedish | `*_core_news_lg` |
| Americas | Portuguese (Brazil), Spanish (LATAM) | `pt/es_core_news_lg` |
| APAC | Japanese, Chinese, Korean | `ja/zh/xx` models |

```bash
python -m spacy download de_core_news_lg   # German
python -m spacy download fr_core_news_lg   # French
python -m spacy download pt_core_news_lg   # Portuguese
```

---

## Scaling

Both services share the same Docker image. Scale them independently:

```bash
# Scale MCP server for more concurrent agent connections
docker compose up --scale mcp-server=3

# Scale REST API for higher HTTP throughput
docker compose up --scale rest-api=2
```

For Azure Container Apps:
```bash
az containerapp update --name mcp-server \
  --min-replicas 2 --max-replicas 20
```

> Add `REDIS_URL` when running multiple REST API pods so rate limit counters are shared across replicas.

---

## Development

```bash
# Run unit tests
pytest tests/unit/ -v

# Run integration tests
pytest tests/integration/ -v

# Run with coverage
pytest tests/unit/ --cov=src --cov-report=html

# Lint and format
ruff check --fix src tests mcp_server
black src tests mcp_server
isort src tests mcp_server
```

---

## Interactive API docs

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- MCP health: http://localhost:8001/health
