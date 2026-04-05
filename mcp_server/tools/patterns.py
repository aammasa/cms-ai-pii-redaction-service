"""
Custom pattern management tools — exposed to AI agents via MCP.

Tools
-----
list_patterns        — list patterns, optionally filtered by business unit
list_business_units  — list available business units
add_custom_pattern   — create a new custom PII pattern
delete_custom_pattern — delete a user-defined pattern by ID
test_regex_pattern   — test regex(es) against sample text without persisting
"""

import logging
import re
from typing import Optional

from ..app import mcp
from src.redaction import custom_patterns
from src.redaction.redactor import mark_analyzer_dirty

logger = logging.getLogger(__name__)


@mcp.tool()
def list_business_units() -> dict:
    """
    List the four supported business units for custom PII patterns.

    Returns:
        {"units": [{id, label, description}, ...]}
    """
    return {"units": custom_patterns.get_business_units()}


@mcp.tool()
def list_patterns(unit: Optional[str] = None) -> dict:
    """
    List all PII patterns (built-in + custom), optionally filtered by business unit.

    Args:
        unit: Business unit ID to filter by. One of:
                'construction', 'agriculture', 'geospatial', 'hr_legal'.
              Omit to return all patterns across all units.

    Returns:
        {
          "patterns": [{
            id, entity_type, label, unit, patterns, context, score, builtin
          }, ...],
          "total": int
        }
    """
    patterns = custom_patterns.get_all_patterns(unit=unit)
    return {"patterns": patterns, "total": len(patterns)}


@mcp.tool()
def add_custom_pattern(
    entity_type: str,
    label: str,
    unit: str,
    patterns: list[str],
    context: Optional[list[str]] = None,
    score: float = 0.80,
    description: str = "",
) -> dict:
    """
    Create a new custom PII pattern for a specific business unit.

    The pattern is persisted immediately and activates on the next redact call.

    Args:
        entity_type: Uppercase identifier for the new entity type.
                     Use uppercase letters, digits, underscores only.
                     Example: 'CONSTR_PROJECT_CODE'
        label:       Human-readable name shown in redacted output and UI.
                     Example: 'Construction Project Code'
        unit:        Business unit this pattern belongs to.
                     One of: 'construction', 'agriculture', 'geospatial', 'hr_legal'
        patterns:    One or more Python regex patterns. Use \\b for word
                     boundaries. Example: ['\\bPROJ-[A-Z]{2}-\\d{4}\\b']
        context:     Optional list of keywords near the match that boost
                     detection confidence. Example: ['project code', 'proj id']
        score:       Base confidence score between 0.0 and 1.0. Default 0.80.
        description: Optional human-readable description of what this ID represents.

    Returns:
        The created pattern record, or {"error": "..."} on failure.
    """
    # Validate entity type format
    if not re.match(r'^[A-Z][A-Z0-9_]+$', entity_type):
        return {"error": "entity_type must be uppercase letters, digits, underscores (e.g. MY_CUSTOM_ID)"}

    valid_units = {u["id"] for u in custom_patterns.get_business_units()}
    if unit not in valid_units:
        return {"error": f"unit must be one of: {', '.join(sorted(valid_units))}"}

    if not patterns:
        return {"error": "At least one regex pattern is required"}

    if not (0.0 <= score <= 1.0):
        return {"error": "score must be between 0.0 and 1.0"}

    # Validate each regex before persisting
    for pat in patterns:
        try:
            re.compile(pat)
        except re.error as exc:
            return {"error": f"Invalid regex '{pat}': {exc}"}

    try:
        record = custom_patterns.create_pattern(
            entity_type=entity_type,
            label=label,
            unit=unit,
            patterns=patterns,
            context=context or [],
            score=score,
            description=description,
        )
        mark_analyzer_dirty()
        logger.info(
            "MCP add_custom_pattern | id=%s | entity=%s | unit=%s",
            record["id"], entity_type, unit,
        )
        return record
    except Exception as exc:
        logger.exception("MCP add_custom_pattern failed")
        return {"error": str(exc)}


@mcp.tool()
def delete_custom_pattern(pattern_id: str) -> dict:
    """
    Delete a user-defined custom pattern by its ID.

    Built-in patterns cannot be deleted. Use list_patterns to find IDs.

    Args:
        pattern_id: The UUID of the pattern to delete.

    Returns:
        {"deleted": true, "id": pattern_id}  on success
        {"error": "..."}                      on failure
    """
    pattern = custom_patterns.get_pattern_by_id(pattern_id)
    if pattern is None:
        return {"error": f"Pattern '{pattern_id}' not found"}
    if pattern.get("builtin"):
        return {"error": "Built-in patterns are read-only and cannot be deleted"}

    try:
        custom_patterns.delete_pattern(pattern_id)
        mark_analyzer_dirty()
        logger.info("MCP delete_custom_pattern | id=%s", pattern_id)
        return {"deleted": True, "id": pattern_id}
    except Exception as exc:
        logger.exception("MCP delete_custom_pattern failed")
        return {"error": str(exc)}


@mcp.tool()
def test_regex_pattern(patterns: list[str], sample_text: str) -> dict:
    """
    Test one or more regex patterns against sample text without persisting anything.

    Use this to validate a pattern before calling add_custom_pattern.

    Args:
        patterns:    List of Python regex strings to test.
        sample_text: Text to search for matches.

    Returns:
        {
          "matches": [{match, start, end, pattern}, ...],
          "match_count": int
        }
        or {"error": "..."} if a regex is invalid.
    """
    matches: list[dict] = []
    for pat in patterns:
        try:
            for m in re.finditer(pat, sample_text, re.IGNORECASE):
                matches.append({
                    "match":   m.group(),
                    "start":   m.start(),
                    "end":     m.end(),
                    "pattern": pat,
                })
        except re.error as exc:
            return {"error": f"Invalid regex '{pat}': {exc}"}

    return {"matches": matches, "match_count": len(matches)}
