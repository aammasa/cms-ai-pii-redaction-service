"""
Custom PII pattern storage and CRUD.

Built-in patterns cover four business units (Construction, Agriculture,
Geospatial, HR/Legal).  User-defined patterns are persisted to
``data/custom_patterns.json`` relative to the project root.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Persistence path ──────────────────────────────────────────────────────────

_DATA_DIR     = Path(__file__).resolve().parents[2] / "data"
_PATTERNS_FILE = _DATA_DIR / "custom_patterns.json"

# ── Business unit catalogue ───────────────────────────────────────────────────

BUSINESS_UNITS: list[dict] = [
    {
        "id": "construction",
        "label": "Construction",
        "description": "Project bid numbers, subcontractor IDs, site coordinates, permit numbers",
    },
    {
        "id": "agriculture",
        "label": "Agriculture",
        "description": "Farm IDs, GPS parcel coordinates, crop yield data linked to a farmer",
    },
    {
        "id": "geospatial",
        "label": "Geospatial",
        "description": "Survey license numbers, geodetic control point IDs",
    },
    {
        "id": "hr_legal",
        "label": "HR / Legal",
        "description": "Employee IDs, internal cost codes, contract reference numbers",
    },
]

# ── Pre-built patterns ────────────────────────────────────────────────────────

BUILTIN_PATTERNS: list[dict] = [
    # ── Construction ──────────────────────────────────────────────────────────
    {
        "id": "builtin_constr_bid",
        "entity_type": "CONSTR_BID_NUMBER",
        "label": "Bid / Tender Number",
        "description": "Construction project bid or tender reference",
        "unit": "construction",
        "patterns": [r"\bBID-\d{4}-\d{4,8}\b", r"\bTENDER-\d{4,10}\b", r"\bRFP-\d{4,10}\b"],
        "context": ["bid", "project bid", "tender", "rfp", "rfq", "solicitation"],
        "score": 0.85,
        "builtin": True,
    },
    {
        "id": "builtin_constr_permit",
        "entity_type": "CONSTR_PERMIT_NUMBER",
        "label": "Building Permit Number",
        "description": "Construction or building permit issued by a municipality",
        "unit": "construction",
        "patterns": [r"\bPRM-\d{4}-\d{4,8}\b", r"\bPERMIT-\d{4,10}\b", r"\bBP-\d{4}-\d{4,8}\b"],
        "context": ["permit", "building permit", "construction permit", "permit number"],
        "score": 0.85,
        "builtin": True,
    },
    {
        "id": "builtin_constr_subcontractor",
        "entity_type": "CONSTR_SUBCONTRACTOR_ID",
        "label": "Subcontractor ID",
        "description": "Subcontractor or vendor registration identifier",
        "unit": "construction",
        "patterns": [r"\bSUB-\d{4,8}\b", r"\bSUBC-\d{4,8}\b"],
        "context": ["subcontractor", "sub-contractor", "sub id", "vendor id", "subc"],
        "score": 0.80,
        "builtin": True,
    },
    {
        "id": "builtin_constr_site",
        "entity_type": "CONSTR_SITE_CODE",
        "label": "Construction Site Code",
        "description": "Internal site or project location code",
        "unit": "construction",
        "patterns": [r"\bSITE-[A-Z]{2,4}-\d{3,6}\b"],
        "context": ["site code", "job site", "site id", "project site"],
        "score": 0.80,
        "builtin": True,
    },
    # ── Agriculture ───────────────────────────────────────────────────────────
    {
        "id": "builtin_agri_farm",
        "entity_type": "AGRI_FARM_ID",
        "label": "Farm Registration ID",
        "description": "Unique farm or grower registration number",
        "unit": "agriculture",
        "patterns": [r"\bFARM-[A-Z0-9]{6,12}\b", r"\bFID-\d{6,10}\b"],
        "context": ["farm id", "farm registration", "grower id", "farm number", "fid"],
        "score": 0.85,
        "builtin": True,
    },
    {
        "id": "builtin_agri_parcel",
        "entity_type": "AGRI_PARCEL_ID",
        "label": "Agricultural Parcel ID",
        "description": "Field or land parcel identifier (e.g. USDA CLU, EU LPIS)",
        "unit": "agriculture",
        "patterns": [r"\bPARCEL-[A-Z0-9]{4,12}\b", r"\bCLU-\d{10,12}\b", r"\bLPIS-[A-Z]{2}-\d{6,10}\b"],
        "context": ["parcel", "parcel id", "clu", "field boundary", "land parcel", "lpis"],
        "score": 0.80,
        "builtin": True,
    },
    {
        "id": "builtin_agri_yield",
        "entity_type": "AGRI_YIELD_RECORD",
        "label": "Crop Yield Record ID",
        "description": "Unique identifier for a per-farmer crop yield entry",
        "unit": "agriculture",
        "patterns": [r"\bYLD-[A-Z]{2,4}-\d{4}-\d{4,8}\b"],
        "context": ["yield record", "crop yield", "harvest record", "yld"],
        "score": 0.80,
        "builtin": True,
    },
    # ── Geospatial ────────────────────────────────────────────────────────────
    {
        "id": "builtin_geo_survey_license",
        "entity_type": "GEO_SURVEY_LICENSE",
        "label": "Survey License Number",
        "description": "Licensed Land Surveyor (LS) or Professional Surveyor (PS) number",
        "unit": "geospatial",
        "patterns": [r"\bSLS-[A-Z]{2}-\d{4,8}\b", r"\bLS\s?\d{4,6}\b", r"\bPS\s?\d{4,6}\b"],
        "context": ["survey license", "licensed surveyor", "ls number", "ps number", "surveyor license"],
        "score": 0.85,
        "builtin": True,
    },
    {
        "id": "builtin_geo_control_point",
        "entity_type": "GEO_CONTROL_POINT_ID",
        "label": "Geodetic Control Point ID",
        "description": "NGS benchmark or horizontal/vertical control station ID",
        "unit": "geospatial",
        "patterns": [r"\bNGS-[A-Z0-9]{6,10}\b", r"\bCP-\d{4}-[A-Z0-9]{4,8}\b"],
        "context": ["control point", "benchmark", "geodetic mark", "ngs", "horizontal control", "vertical control"],
        "score": 0.80,
        "builtin": True,
    },
    # ── HR / Legal ────────────────────────────────────────────────────────────
    {
        "id": "builtin_hr_employee",
        "entity_type": "HR_EMPLOYEE_ID",
        "label": "Employee ID",
        "description": "Internal employee or staff identifier",
        "unit": "hr_legal",
        "patterns": [r"\bEMP-\d{4,8}\b", r"\bEMPL-\d{4,8}\b", r"\bSTAFF-\d{4,8}\b"],
        "context": ["employee id", "employee number", "emp id", "staff id", "worker id", "personnel id"],
        "score": 0.85,
        "builtin": True,
    },
    {
        "id": "builtin_hr_cost_code",
        "entity_type": "HR_COST_CODE",
        "label": "Internal Cost Code",
        "description": "Internal cost centre or WBS billing code",
        "unit": "hr_legal",
        "patterns": [r"\bCC-[A-Z]{2,4}-\d{4,8}\b", r"\bCOST-\d{4,10}\b", r"\bWBS-[A-Z0-9]{4,12}\b"],
        "context": ["cost code", "internal cost", "charge code", "billing code", "wbs", "cost centre"],
        "score": 0.80,
        "builtin": True,
    },
    {
        "id": "builtin_hr_contract",
        "entity_type": "HR_CONTRACT_REF",
        "label": "Contract Reference Number",
        "description": "Legal contract or agreement reference identifier",
        "unit": "hr_legal",
        "patterns": [r"\bCNT-\d{4}-[A-Z0-9]{4,10}\b", r"\bCONTRACT-\d{4,10}\b", r"\bAGR-\d{4,10}\b"],
        "context": ["contract", "contract ref", "contract number", "agreement number", "agreement ref"],
        "score": 0.85,
        "builtin": True,
    },
]


# ── Persistence helpers ────────────────────────────────────────────────────────

def _load_file() -> list[dict]:
    if not _PATTERNS_FILE.exists():
        return []
    with open(_PATTERNS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_file(patterns: list[dict]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_PATTERNS_FILE, "w", encoding="utf-8") as f:
        json.dump(patterns, f, indent=2, ensure_ascii=False)


# ── Public CRUD ────────────────────────────────────────────────────────────────

def get_all_patterns(unit: Optional[str] = None) -> list[dict]:
    """Return built-in + user-defined patterns, optionally filtered by unit."""
    custom = _load_file()
    all_patterns = BUILTIN_PATTERNS + custom
    if unit:
        all_patterns = [p for p in all_patterns if p["unit"] == unit]
    return all_patterns


def get_pattern_by_id(pattern_id: str) -> Optional[dict]:
    for p in BUILTIN_PATTERNS:
        if p["id"] == pattern_id:
            return p
    for p in _load_file():
        if p["id"] == pattern_id:
            return p
    return None


def create_pattern(
    entity_type: str,
    label: str,
    unit: str,
    patterns: list[str],
    context: list[str],
    score: float,
    description: str = "",
) -> dict:
    """Persist a new custom pattern and return it."""
    record: dict = {
        "id": str(uuid.uuid4()),
        "entity_type": entity_type,
        "label": label,
        "description": description or label,
        "unit": unit,
        "patterns": patterns,
        "context": context,
        "score": score,
        "builtin": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    existing = _load_file()
    existing.append(record)
    _save_file(existing)
    logger.info(
        "Custom pattern created | id=%s | entity=%s | unit=%s",
        record["id"], entity_type, unit,
    )
    return record


def delete_pattern(pattern_id: str) -> bool:
    """
    Delete a user-defined pattern by ID.

    Returns True if deleted.  Returns False if the ID belongs to a built-in
    pattern (those are read-only) or if the ID doesn't exist.
    """
    if any(p["id"] == pattern_id for p in BUILTIN_PATTERNS):
        return False  # built-ins are read-only
    existing = _load_file()
    filtered = [p for p in existing if p["id"] != pattern_id]
    if len(filtered) == len(existing):
        return False  # not found
    _save_file(filtered)
    logger.info("Custom pattern deleted | id=%s", pattern_id)
    return True


def get_business_units() -> list[dict]:
    return BUSINESS_UNITS


def as_recognizer_defs(unit: Optional[str] = None) -> list[dict]:
    """
    Return patterns in the same shape as ``CUSTOM_RECOGNIZER_DEFS`` in
    ``redactor.py`` so they can be registered as Presidio PatternRecognizers.
    """
    return [
        {
            "entity":      p["entity_type"],
            "label":       p["label"],
            "description": p.get("description", p["label"]),
            "patterns":    p["patterns"],
            "context":     p["context"],
            "score":       p["score"],
            "native_lang": "en",
        }
        for p in get_all_patterns(unit=unit)
    ]
