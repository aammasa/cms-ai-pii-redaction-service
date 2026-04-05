"""
MCP server entry point — mirrors the pattern of main.py for the REST API.

Usage
-----
uvicorn mcp_main:app --host 0.0.0.0 --port 8001 --reload
"""

from mcp_server.server import app  # noqa: F401
