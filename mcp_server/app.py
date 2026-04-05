"""
Shared FastMCP instance.

Imported by every tool module so tools self-register via @mcp.tool().
server.py imports this instance last and calls .sse_app() to get
the ASGI application.
"""

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(
    name="PII Redaction & Summarization",
    instructions=(
        "Redact PII from text and documents across multiple languages, "
        "manage per-business-unit custom patterns, and summarize clean output via Claude."
    ),
    # DNS rebinding protection disabled — auth is handled by MCPAPIKeyMiddleware
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
