"""
Redaction tools — exposed to AI agents via MCP.

Tools
-----
redact_text   — detect and redact PII from plain text
list_entities — list all supported PII entity types
list_languages — list supported languages and NLP model status
"""

import logging
from typing import Optional

from ..app import mcp
from src.redaction.redactor import (
    detect_language,
    get_supported_entities,
    get_supported_languages,
    redact_text as _redact_text,
)

logger = logging.getLogger(__name__)


@mcp.tool()
def redact_text(
    text: str,
    language: str = "auto",
    entities: Optional[list[str]] = None,
    operator: str = "replace",
) -> dict:
    """
    Detect and redact PII from plain text.

    Args:
        text:     The text to analyse and redact.
        language: ISO 639-1 language code (e.g. 'en', 'de', 'fr') or 'auto'
                  to detect automatically. Defaults to 'auto'.
        entities: List of entity type IDs to detect (e.g. ['PERSON',
                  'EMAIL_ADDRESS']). Omit to detect all supported types.
        operator: How to anonymize detected PII.
                    'replace' — substitute with <ENTITY_TYPE> tag  (default)
                    'redact'  — delete the span entirely
                    'mask'    — replace chars with *
                    'hash'    — replace with SHA-256 hex digest

    Returns:
        {
          "redacted_text":   str,
          "entities_found":  [{type, start, end, score, original}, ...],
          "entity_counts":   {entity_type: count, ...},
          "detected_language": str
        }
    """
    if operator not in ("replace", "redact", "mask", "hash"):
        return {"error": f"Invalid operator '{operator}'. Use: replace | redact | mask | hash"}

    try:
        result = _redact_text(
            text=text,
            language=language,
            entities=entities,
            operator=operator,
        )
        logger.info(
            "MCP redact_text | lang=%s | operator=%s | pii=%d",
            result["detected_language"], operator, len(result["entities_found"]),
        )
        return result
    except Exception as exc:
        logger.exception("MCP redact_text failed")
        return {"error": str(exc)}


@mcp.tool()
def list_entities() -> dict:
    """
    List all PII entity types supported by this service.

    Returns a list of objects with 'id', 'label', and 'description' fields,
    including built-in Presidio entities and all active custom patterns.

    Returns:
        {"entities": [{id, label, description}, ...]}
    """
    return {"entities": get_supported_entities()}


@mcp.tool()
def list_languages() -> dict:
    """
    List all supported languages and whether their spaCy NLP model is installed.

    Languages without an installed model fall back to English NLP for name/org
    detection while regex-based recognizers (email, phone, country IDs) remain
    active for all languages.

    Returns:
        {"languages": [{code, label, installed}, ...]}
    """
    return {"languages": get_supported_languages()}
