"""
Summarization tool — exposed to AI agents via MCP.

Tools
-----
summarize_text — summarize PII-free text via Claude (or extractive fallback)
"""

import logging

from ..app import mcp
from src.summarization.summarizer import summarize_text as _summarize_text
from src.constants import LLM_MODEL

logger = logging.getLogger(__name__)


@mcp.tool()
def summarize_text(redacted_text: str, length: str = "short") -> dict:
    """
    Summarize PII-free text using Claude.

    Always run redact_text first to ensure no PII is included in the summary
    prompt sent to the LLM.

    Args:
        redacted_text: Text with PII already removed/replaced.
        length:        Summary verbosity.
                         'short'    — 1-2 sentences  (default)
                         'medium'   — 1 paragraph
                         'detailed' — structured multi-paragraph summary

    Returns:
        {
          "summary":   str,
          "llm_model": str   (model used, or 'extractive' if no API key)
        }

    Note:
        Falls back to an extractive summary if ANTHROPIC_API_KEY is not set.
    """
    if length not in ("short", "medium", "detailed"):
        return {"error": f"Invalid length '{length}'. Use: short | medium | detailed"}

    try:
        import os
        summary = _summarize_text(redacted_text=redacted_text, length=length)
        llm_model = LLM_MODEL if os.environ.get("ANTHROPIC_API_KEY") else "extractive"
        logger.info("MCP summarize_text | length=%s | model=%s", length, llm_model)
        return {"summary": summary, "llm_model": llm_model}
    except Exception as exc:
        logger.exception("MCP summarize_text failed")
        return {"error": str(exc)}
