"""
Shared FastMCP instance.

Imported by every tool module so tools self-register via @mcp.tool().
server.py imports this instance last and calls .sse_app() to get
the ASGI application.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="PII Redaction & Summarization",
    instructions=(
        "Redact PII from text and documents across multiple languages, "
        "manage per-business-unit custom patterns, and summarize clean output via Claude."
    ),
)
