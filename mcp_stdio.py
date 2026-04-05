"""
stdio entry point for Claude Desktop.

Claude Desktop spawns this script as a subprocess and communicates via
stdin/stdout (stdio transport).  The SSE server (mcp_main.py / port 8001)
is still used for remote AI agents and Trimble-wide access.

Usage (set in claude_desktop_config.json — do NOT run directly)
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path when spawned by Claude Desktop
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Load .env so ANTHROPIC_API_KEY and other vars are available
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent / ".env")

# Import tool modules — side-effects register @mcp.tool() decorators
from mcp_server.app import mcp          # noqa: E402
from mcp_server.tools import patterns   # noqa: E402, F401
from mcp_server.tools import redact     # noqa: E402, F401
from mcp_server.tools import summarize  # noqa: E402, F401

if __name__ == "__main__":
    mcp.run()  # stdio transport — Claude Desktop reads/writes via stdin/stdout
