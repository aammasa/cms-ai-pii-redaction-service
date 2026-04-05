---
applyTo: '**'
---
# Agent Instructions

This file provides guidance to the AI Agent when working with code in this repository.

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the API
uvicorn src.api:api --host 0.0.0.0 --port 8000

# Run unit tests (mocked, no Azure resources needed)
pytest tests/unit/ -v

# Run a specific test
pytest tests/unit/test_guardrails_unit.py -v -k test_shield_prompt_success

# Run with coverage
pytest tests/unit/ --cov=src --cov-report=html

# Run integration tests (requires Azure resources and .env variables)
pytest tests/integration/ -v

# Lint and format code
ruff check --fix src tests
black src tests
isort src tests

# Or check without fixing
ruff check src tests
black --check src tests
```

## Architecture

Tech stack: 
1. FastAPI with uvicorn, Python 3.11+ (3.13 supported), async/await. 

External services: 
1. Azure Cosmos DB, 
2. Blob Storage, 
3. AI Search, Document Intelligence, 
4. Service Bus, 
5. Content Safety, 
6. OpenAI, 
7. Google Drive API. 

The application is an API service that accepts long-running data processing jobs (web scraping, document analysis, video transcription) and tracks them via Cosmos DB.

Background worker (`src/data_ingestion/data_change_worker.py`) consumes jobs from Azure Service Bus queue and updates job status. All external credentials loaded via environment variables from `.env` file (never hardcoded).

**Target architecture (in progress — new code must follow this, existing code migrates incrementally):**
```
Router → Service → Database Client → Database
              └→ Networking Client → External API
```
Routers handle HTTP only. Services contain business logic. Clients encapsulate external calls. Do not put business logic in routers or direct external calls in services.

## Conventions

**Naming:**
- Python files: snake_case
- Classes: PascalCase (models use Pydantic BaseModel)
- Functions: snake_case
- API router prefixes: lowercase with hyphens (e.g., `/web-scraping`, `/document-intelligence`)
- Environment variables: UPPERCASE_WITH_UNDERSCORES

**File organisation:**
- `src/api.py` — FastAPI app initialization and router registration
- `src/worker.py` — Background worker consuming Service Bus messages
- `src/models.py` — All Pydantic DTOs (request/response models). All new DTOs go here, not inline in routers or domain modules.
- `src/constants.py` — Hardcoded constants and env var keys
- `src/cosmos_config.py` — Cosmos DB client initialization
- `src/routers/` — API route handlers (one file per domain: web_scraping.py, document_intelligence.py, etc.)
- `src/[domain]/` — Domain-specific service logic (e.g., `web_scraping/`, `data_funnel/`)
- `src/util/` — Shared reusable utilities. Always check here before writing new helper logic.
- `tests/unit/` — Unit tests with mocked dependencies
- `tests/integration/` — Integration tests hitting real Azure services
- `tests/utils/` — Shared fixtures and mock data

**Utility modules (`src/util/`):**
Always check `src/util/` before writing new helper logic — prefer reuse over duplication. Key modules:
- `azure_storage_utils.py` — all Azure Blob Storage operations (upload, download, list, delete). Use this for any blob work.
- `update_job_status.py` — async job lifecycle: `create_job`, `get_job`, `update_job`. Every async endpoint must track its job status through this module.
- `google_drive_handler.py`, `google_drive_copy_handler.py` — Google Drive operations.
- `google_space_notifier.py` — Google Chat notifications.

If an existing util method almost fits but needs a change, do **not** modify it unilaterally. Present the gap, propose the change with impact analysis, and wait for explicit user approval.

**Async:**
Selective async/await. Routers use async endpoints where needed (e.g., long-running operations with BackgroundTasks). Most domain logic is synchronous. Background worker uses asyncio for message handling. All async endpoints must track job status via `src/util/update_job_status.py`.

**Data access:**
Currently, Cosmos DB operations use the Azure SDK directly (no ORM/service layer abstraction). New code should follow the target architecture: `Service → Database Client → Database`. Blob operations via `src/util/azure_storage_utils.py` (not raw BlobServiceClient). Job status via `src/util/update_job_status.py`.

**Error handling, input validation, and logging:**
Detailed standards for all three are in `@.github/instructions/design.instructions.md` (see **Implementation standards**). Summary:
- Validate request bodies with Pydantic `Field` constraints; query/path params with `Query`/`Path` constraints; add `ValueError` guards in utility methods called outside router context.
- Domain exceptions are defined in `src/errors/exceptions.py` and converted to HTTP responses via global handlers in `src/errors/exception_handlers.py` — routers must not repeat `try/except` for these.
- Log with `logging.getLogger(__name__)`; use `info`/`warning`/`error` levels appropriately; never use `print()` or log credentials.

**Import statements:**
Always place all import statements at the top of the file, grouped in the standard PEP 8 order: standard library imports, third-party imports, then local application imports — each group separated by a blank line. Inline or deferred imports are only acceptable when required to avoid circular imports or for optional/conditional dependencies that should not be loaded at module startup.

**API patterns:**
Request models inherit from Pydantic BaseModel. Response format varies by endpoint—usually dict or list. Query parameters for filtering/options. All endpoints except webhooks require API key header (configurable name via API_KEY_HEADER env var, default X-API-Key).

## Libraries

**Allowed (actively used):**
- fastapi[standard], uvicorn
- azure-storage-blob, azure-identity, azure-search-documents, azure-cosmos, azure-servicebus, azure-ai-documentintelligence, azure-ai-textanalytics
- pydantic
- httpx (for async HTTP in tests)
- pytest, pytest-mock, pytest-asyncio, pytest-cov
- ruff, black, isort
- scrapy, beautifulsoup4 (web scraping)
- google-api-python-client, google-auth (Google Drive integration)
- openai
- python-dotenv, python-multipart, webvtt-py, yt-dlp

**Prohibited (new code only — existing usages will be migrated incrementally):**
- requests — use httpx instead. Existing integration tests still use requests (see testing.instructions.md); all new code must use httpx.
- pytest.mark.skip without a reason — always provide a reason argument: `@pytest.mark.skip(reason="...")`. Bare `pytest.skip()` calls in test bodies are discouraged in newer pytest versions.
- Unpinned or vulnerable library versions in `requirements.txt` — when adding a new dependency, always pin it to a specific version (e.g., `httpx==0.27.0`) that has no known CVEs. Verify the version against the PyPI advisory database or a vulnerability scanner before adding it. Never use unbounded version specifiers (e.g., `httpx>=0.20`) for new additions.

**Patterns:**
- Always use Pydantic v1 API (BaseModel, Field, validator patterns seen in models.py)
- HTTP clients: Use Azure SDK clients for Azure services, httpx for external HTTP
- Import all fixtures in tests/conftest.py from tests.utils package
- Mock Azure SDK clients (not the whole module), patch at import site (e.g., @patch('src.document_intelligence.docintl.blob_service_client'))

## Testing

Framework: pytest with pytest-cov, pytest-mock, pytest-asyncio. Run via `pytest tests/unit/` or `pytest tests/integration/`.

**Key fixtures (from tests/utils/fixtures.py):**
- `api_client` — `TestClient` with `verify_api_key` overridden for endpoint tests
- `auth_headers` — test API key header
- `mock_cosmos_client`, `mock_blob_service_client` — pre-configured Azure mocks
- `mock_env_vars` — `monkeypatch`-based env var setup (auto-cleaned per test)

**Patterns:**
- Mock Azure SDK clients at their import location via `@patch('src.module.client_name')`
- Use mock_data (MOCK_BLOBS, MOCK_JOB_STATUS, etc.) from tests/utils/mock_data.py
- Integration tests apply `@pytest.mark.integration` marker and use real credentials from .env

**When working on tests, see `.github/instructions/testing.instructions.md` for detailed standards:** AAA pattern, naming conventions (test_<method>_<scenario>_<expected_outcome>), dependency isolation, mock/patch patterns, and factory guidelines.

**Required before shipping:**
- Unit tests written for new routers/functions
- Integration test added if new endpoint or external service call
- All tests pass: `pytest tests/unit/`
- No lint violations: `ruff check src` and `black --check src`

## Security

**Credential handling:**
All secrets via environment variables loaded with python-dotenv. API_KEY for authentication set via env var. Never hardcode credentials. .env file ignored in git (.gitignore).

**Auth:**
API Key authentication via verify_api_key dependency injected on all routers. Header name configurable via API_KEY_HEADER env var. Webhook routes explicitly excluded from authentication.

## Rules index

- Design standards and principles: @.github/instructions/design.instructions.md
- Input validation, exception handling, logging: @.github/instructions/design.instructions.md (Implementation standards)
- Testing standards and patterns: @.github/instructions/testing.instructions.md

## Post-implementation recommendation

After completing any implementation task:
1. Surface one improvement as a Socratic question — ask what might fail or go wrong in the current code without this improvement. The improvement can relate to any area: scalability, performance, maintainability, testability, observability, security, simplicity, or alignment with the target architecture.
2. When the user answers, explain the reasoning and provide the concrete `Recommendation:`.

Keep each step to 1–3 sentences. Do not bundle multiple suggestions.

## Definition of done

A feature is complete only when:
- [ ] Code follows naming, file organisation, and async conventions above
- [ ] Unit tests written and passing (`pytest tests/unit/ -v`)
- [ ] Integration test added if new endpoint or external service call
- [ ] `ruff check --fix` and `black` pass with no changes
- [ ] No security issues (no hardcoded secrets, proper input validation)
- [ ] All tests pass (`pytest tests/`)