"""FastAPI application initialisation and router registration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .errors.exception_handlers import (
    extraction_error_handler,
    redaction_error_handler,
    summarization_error_handler,
)
from .errors.exceptions import ExtractionError, RedactionError, SummarizationError
from .routers import health, patterns, redaction, summarization
from .util.logging_config import configure_logging
from .util.rate_limit import limiter

configure_logging()

api = FastAPI(
    title="PII Redaction API",
    description=(
        "Extract text from documents, detect and redact PII across multiple languages, "
        "and summarize the clean output."
    ),
    version="2.0.0",
)

# ── Rate limiter state ─────────────────────────────────────────────────────────

api.state.limiter = limiter

# ── Middleware ─────────────────────────────────────────────────────────────────

api.add_middleware(SlowAPIMiddleware)
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global exception handlers ──────────────────────────────────────────────────

api.add_exception_handler(ExtractionError,    extraction_error_handler)
api.add_exception_handler(RedactionError,     redaction_error_handler)
api.add_exception_handler(SummarizationError, summarization_error_handler)
api.add_exception_handler(RateLimitExceeded,  _rate_limit_exceeded_handler)

# ── Routers ────────────────────────────────────────────────────────────────────

api.include_router(health.router)
api.include_router(redaction.router)
api.include_router(summarization.router)
api.include_router(patterns.router)

# ── MCP SSE server — mounted at /mcp ──────────────────────────────────────────
# Endpoints:  GET /mcp/sse          (SSE stream)
#             POST /mcp/messages/   (tool calls)
#             GET /mcp/health

from mcp_server.server import create_app as _create_mcp_app  # noqa: E402

api.mount("/mcp", _create_mcp_app(root_path="/mcp"))
