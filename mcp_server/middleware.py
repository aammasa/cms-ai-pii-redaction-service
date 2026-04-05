"""
API key authentication middleware for the MCP server.

When MCP_API_KEY is set in the environment, every incoming request must
include the key as:
    Authorization: Bearer <key>
or
    X-MCP-Key: <key>

The /health endpoint is always exempt from authentication.

When MCP_API_KEY is not set, auth is disabled (development mode).
"""

import logging
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

ENV_MCP_API_KEY = "MCP_API_KEY"

logger = logging.getLogger(__name__)


class MCPAPIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Health check is always public
        if request.url.path == "/health":
            return await call_next(request)

        mcp_key = os.environ.get(ENV_MCP_API_KEY)
        if not mcp_key:
            # Auth disabled — development mode
            return await call_next(request)

        # Accept key via Authorization: Bearer <key> or X-MCP-Key: <key>
        auth_header = request.headers.get("Authorization", "")
        key_header  = request.headers.get("X-MCP-Key", "")

        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif key_header:
            token = key_header.strip()

        if not token or token != mcp_key:
            logger.warning(
                "MCP auth failed | path=%s | ip=%s",
                request.url.path,
                request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                {"detail": "Unauthorized — provide MCP_API_KEY via 'Authorization: Bearer <key>' or 'X-MCP-Key: <key>'"},
                status_code=401,
            )

        return await call_next(request)
