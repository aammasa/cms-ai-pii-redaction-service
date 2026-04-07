"""
MCP server — ASGI application factory.

Architecture
------------
FastMCP instance (app.py)
    ↑ tools register via @mcp.tool() (imported below for side-effects)
    ↓ mcp.sse_app()              → legacy SSE transport
    ↓ mcp.streamable_http_app() → modern Streamable HTTP transport (Postman/Claude)
        ↓ wrapped with MCPAPIKeyMiddleware + /health route
            ↓ exported as `app` for uvicorn

Endpoints (when mounted at /mcp in api.py)
------------------------------------------
GET  /mcp/health        — liveness check (no auth required)
GET  /mcp/sse           — SSE stream (legacy clients)
POST /mcp/messages/     — SSE message endpoint
POST /mcp/http          — Streamable HTTP (Postman, Claude Desktop remote)

Tools registered
----------------
redact_text, list_entities, list_languages       (tools/redact.py)
summarize_text                                   (tools/summarize.py)
list_business_units, list_patterns,
add_custom_pattern, delete_custom_pattern,
test_regex_pattern                               (tools/patterns.py)
"""

import logging

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from src.util.logging_config import configure_logging

configure_logging()

logger = logging.getLogger(__name__)

# ── Import tool modules — side-effects register @mcp.tool() decorators ────────
from .app import mcp  # noqa: E402  (must come after logging config)
from .middleware import MCPAPIKeyMiddleware  # noqa: E402
from .tools import patterns, redact, summarize  # noqa: E402, F401

logger.info(
    "MCP tools registered: %s",
    [t.name for t in mcp._tool_manager.list_tools()],
)


# ── Health endpoint ────────────────────────────────────────────────────────────

async def health(request: Request) -> JSONResponse:
    tools = [t.name for t in mcp._tool_manager.list_tools()]
    return JSONResponse({
        "status": "ok",
        "service": "mcp-pii-redaction",
        "transport": "sse",
        "tools": tools,
        "tool_count": len(tools),
    })


# ── ASGI app ───────────────────────────────────────────────────────────────────

def create_app() -> Starlette:
    sse_starlette  = mcp.sse_app()
    http_starlette = mcp.streamable_http_app()

    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Mount("/http", app=http_starlette),
            Mount("/", app=sse_starlette),
        ],
        middleware=[
            Middleware(MCPAPIKeyMiddleware),
        ],
    )


app = create_app()
