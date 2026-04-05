"""All Pydantic request/response DTOs. New models must be added here, not inline in routers."""

from typing import Optional

from pydantic import BaseModel, Field


# ── Redaction ─────────────────────────────────────────────────────────────────

class RedactRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Plain text to redact")
    language: str = Field("auto", description="ISO 639-1 code or 'auto' for auto-detection")
    entities: Optional[list[str]] = Field(None, description="Entity IDs to scan for; omit for all")
    operator: str = Field(
        "replace",
        pattern="^(replace|redact|mask|hash)$",
        description="Anonymization operator: replace | redact | mask | hash",
    )
    session_id: Optional[str] = Field(None, description="Groups related trace events in Log Analytics")


class RedactResponse(BaseModel):
    original_text: str
    redacted_text: str
    entities_found: list[dict]
    entity_counts: dict[str, int]
    detected_language: str


# ── Process (file upload) ─────────────────────────────────────────────────────

class ProcessResponse(BaseModel):
    original_text: str
    redacted_text: str
    entities_found: list[dict]
    entity_counts: dict[str, int]
    detected_language: str
    filename: str
    file_type: str
    session_id: str


# ── Summarization ─────────────────────────────────────────────────────────────

class SummarizeRequest(BaseModel):
    redacted_text: str = Field(..., min_length=1, description="PII-free text to summarize")
    length: str = Field(
        "short",
        pattern="^(short|medium|detailed)$",
        description="Summary length: short | medium | detailed",
    )
    session_id: Optional[str] = Field(None, description="Groups related trace events in Log Analytics")


class SummarizeResponse(BaseModel):
    summary: str


# ── Catalogue endpoints ───────────────────────────────────────────────────────

class EntitiesResponse(BaseModel):
    entities: list[dict]  # [{id, label, description}]


class LanguagesResponse(BaseModel):
    languages: list[dict]  # [{code, label, installed}]


# ── Custom PII patterns ───────────────────────────────────────────────────────

class PatternCreateRequest(BaseModel):
    entity_type: str = Field(
        ...,
        min_length=2,
        pattern=r"^[A-Z][A-Z0-9_]{1,}$",
        description="Uppercase entity type identifier, e.g. MY_CUSTOM_ID",
    )
    label: str = Field(..., min_length=2, max_length=80, description="Human-readable label")
    description: str = Field("", max_length=200, description="Optional description")
    unit: str = Field(
        ...,
        pattern="^(construction|agriculture|geospatial|hr_legal)$",
        description="Business unit: construction | agriculture | geospatial | hr_legal",
    )
    patterns: list[str] = Field(..., min_length=1, description="List of regex patterns")
    context: list[str] = Field(default_factory=list, description="Context keywords that boost match confidence")
    score: float = Field(0.80, ge=0.0, le=1.0, description="Base confidence score (0–1)")


class PatternResponse(BaseModel):
    id: str
    entity_type: str
    label: str
    description: str = ""
    unit: str
    patterns: list[str]
    context: list[str]
    score: float
    builtin: bool
    created_at: Optional[str] = None


class PatternListResponse(BaseModel):
    patterns: list[dict]


class BusinessUnitsResponse(BaseModel):
    units: list[dict]


class PatternTestRequest(BaseModel):
    patterns: list[str] = Field(..., min_length=1, description="Regex patterns to test")
    sample_text: str = Field(..., min_length=1, description="Text to run the patterns against")


class PatternTestResponse(BaseModel):
    matches: list[dict]
    match_count: int


