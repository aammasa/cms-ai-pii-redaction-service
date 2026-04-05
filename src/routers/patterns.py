"""Pattern management routes — /patterns. HTTP handling only."""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from ..models import (
    BusinessUnitsResponse,
    PatternCreateRequest,
    PatternListResponse,
    PatternResponse,
    PatternTestRequest,
    PatternTestResponse,
)
from ..redaction import custom_patterns
from ..redaction.redactor import mark_analyzer_dirty
from ..util.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/patterns",
    tags=["patterns"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("", response_model=PatternListResponse)
def list_patterns(unit: Optional[str] = None) -> PatternListResponse:
    """List all patterns, optionally filtered by business unit."""
    return PatternListResponse(patterns=custom_patterns.get_all_patterns(unit=unit))


@router.get("/units", response_model=BusinessUnitsResponse)
def list_units() -> BusinessUnitsResponse:
    """List all supported business units."""
    return BusinessUnitsResponse(units=custom_patterns.get_business_units())


@router.post("", response_model=PatternResponse, status_code=201)
def create_pattern(req: PatternCreateRequest) -> PatternResponse:
    """Create a new custom PII pattern for a business unit."""
    # Validate each regex before persisting
    for pat in req.patterns:
        try:
            re.compile(pat)
        except re.error as exc:
            raise HTTPException(status_code=422, detail=f"Invalid regex '{pat}': {exc}") from exc

    record = custom_patterns.create_pattern(
        entity_type=req.entity_type,
        label=req.label,
        unit=req.unit,
        patterns=req.patterns,
        context=req.context,
        score=req.score,
        description=req.description,
    )
    mark_analyzer_dirty()
    logger.info(
        "pattern created | id=%s | entity=%s | unit=%s",
        record["id"], record["entity_type"], record["unit"],
    )
    return PatternResponse(**record)


@router.delete("/{pattern_id}", status_code=204)
def delete_pattern(pattern_id: str) -> None:
    """
    Delete a user-defined pattern by ID.

    Returns 404 if the ID is unknown.
    Returns 403 if the pattern is a built-in (read-only).
    """
    # Check if it's a built-in
    p = custom_patterns.get_pattern_by_id(pattern_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Pattern not found")
    if p.get("builtin"):
        raise HTTPException(status_code=403, detail="Built-in patterns cannot be deleted")

    custom_patterns.delete_pattern(pattern_id)
    mark_analyzer_dirty()
    logger.info("pattern deleted | id=%s", pattern_id)


@router.post("/test", response_model=PatternTestResponse)
def test_pattern(req: PatternTestRequest) -> PatternTestResponse:
    """Test regex patterns against sample text without persisting anything."""
    matches: list[dict] = []
    for pat in req.patterns:
        try:
            for m in re.finditer(pat, req.sample_text, re.IGNORECASE):
                matches.append({
                    "match":   m.group(),
                    "start":   m.start(),
                    "end":     m.end(),
                    "pattern": pat,
                })
        except re.error as exc:
            raise HTTPException(status_code=422, detail=f"Invalid regex '{pat}': {exc}") from exc

    return PatternTestResponse(matches=matches, match_count=len(matches))
