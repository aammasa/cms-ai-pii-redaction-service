"""PII redaction service powered by Microsoft Presidio with multi-language support."""

import logging
from collections import Counter
from typing import Optional

from ..constants import LANGUAGE_LABELS, LANGUAGE_MODELS
from ..errors.exceptions import RedactionError
from . import custom_patterns as _cp

logger = logging.getLogger(__name__)

# ── Country-specific custom recognizer definitions (regex-based) ───────────────

CUSTOM_RECOGNIZER_DEFS: list[dict] = [
    {
        "entity": "DE_PERSONALAUSWEIS",
        "label": "German ID (Personalausweis)",
        "description": "German national identity card number",
        "patterns": [r"\b[LMNPRTVWXY][0-9CDFGHJKLMNPRTVWXYZ]{8}\b"],
        "context": ["ausweis", "personalausweis", "perso", "ausweisnum", "german id"],
        "score": 0.85,
        "native_lang": "de",
    },
    {
        "entity": "FR_NIR",
        "label": "French Social Security (NIR)",
        "description": "French Numéro d'Inscription au Répertoire (NIR)",
        "patterns": [r"\b[12][0-9]{2}(?:0[1-9]|1[0-2]|20)[0-9]{2}[0-9]{3}[0-9]{3}[0-9]{2}\b"],
        "context": ["nir", "sécurité sociale", "securite sociale", "sécu"],
        "score": 0.85,
        "native_lang": "fr",
    },
    {
        "entity": "IN_AADHAAR",
        "label": "Indian Aadhaar",
        "description": "12-digit Indian unique identification number",
        "patterns": [r"\b[2-9][0-9]{3}\s?[0-9]{4}\s?[0-9]{4}\b"],
        "context": ["aadhaar", "aadhar", "uid", "uidai", "unique identification"],
        "score": 0.85,
        "native_lang": "en",
    },
    {
        "entity": "IN_PAN",
        "label": "Indian PAN",
        "description": "Indian Permanent Account Number (tax ID)",
        "patterns": [r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"],
        "context": ["pan", "permanent account number", "income tax", "pancard"],
        "score": 0.85,
        "native_lang": "en",
    },
    {
        "entity": "BR_CPF",
        "label": "Brazilian CPF",
        "description": "Brazilian individual taxpayer registry (CPF)",
        "patterns": [r"\b[0-9]{3}\.?[0-9]{3}\.?[0-9]{3}-?[0-9]{2}\b"],
        "context": ["cpf", "cadastro de pessoas", "pessoa física", "pessoa fisica"],
        "score": 0.75,
        "native_lang": "pt",
    },
    {
        "entity": "BR_CNPJ",
        "label": "Brazilian CNPJ",
        "description": "Brazilian company taxpayer registry (CNPJ)",
        "patterns": [r"\b[0-9]{2}\.?[0-9]{3}\.?[0-9]{3}\/?[0-9]{4}-?[0-9]{2}\b"],
        "context": ["cnpj", "cadastro nacional", "empresa", "razão social"],
        "score": 0.75,
        "native_lang": "pt",
    },
]

SUPPORTED_ENTITIES: list[dict] = [
    {"id": "PERSON",           "label": "Person name",          "description": "Full or partial names of people"},
    {"id": "EMAIL_ADDRESS",    "label": "Email address",         "description": "Email addresses"},
    {"id": "PHONE_NUMBER",     "label": "Phone number",          "description": "Phone and fax numbers"},
    {"id": "CREDIT_CARD",      "label": "Credit card",           "description": "Credit/debit card numbers"},
    {"id": "US_SSN",           "label": "US SSN",                "description": "US Social Security Numbers"},
    {"id": "IP_ADDRESS",       "label": "IP address",            "description": "IPv4 and IPv6 addresses"},
    {"id": "LOCATION",         "label": "Location",              "description": "Countries, cities, addresses"},
    {"id": "DATE_TIME",        "label": "Date / time",           "description": "Dates, times, years"},
    {"id": "URL",              "label": "URL",                   "description": "Web URLs and links"},
    {"id": "IBAN_CODE",        "label": "IBAN",                  "description": "International bank account numbers"},
    {"id": "NRP",              "label": "Nationality / group",   "description": "Nationalities, religions, political groups"},
    {"id": "MEDICAL_LICENSE",  "label": "Medical license",       "description": "Medical license numbers"},
    {"id": "ORGANIZATION",     "label": "Organization",          "description": "Company and org names"},
    *[
        {"id": d["entity"], "label": d["label"], "description": d["description"]}
        for d in CUSTOM_RECOGNIZER_DEFS
    ],
]

# ── Lazy-loaded Presidio singletons ────────────────────────────────────────────
# Deferred to avoid loading heavy NLP models at import time (acceptable per CLAUDE.md).

_analyzer = None
_anonymizer = None
_available_lang_codes: Optional[list[str]] = None


def mark_analyzer_dirty() -> None:
    """
    Invalidate the cached Presidio analyzer so it is rebuilt on the next
    redaction call.  Called whenever custom patterns are added or deleted.
    """
    global _analyzer, _anonymizer
    _analyzer = None
    _anonymizer = None
    logger.info("Presidio analyzer cache invalidated — will rebuild on next request")


def _get_available_lang_codes() -> list[str]:
    global _available_lang_codes
    if _available_lang_codes is not None:
        return _available_lang_codes

    # spaCy is a conditional dependency — only loaded when engines are built
    import spacy  # noqa: PLC0415

    available = [
        code
        for code, model in LANGUAGE_MODELS.items()
        if spacy.util.is_package(model)
    ]
    if "en" not in available:
        available.append("en")
    _available_lang_codes = available
    logger.info("Available NLP languages: %s", available)
    return available


def _build_analyzer():
    from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern  # noqa: PLC0415
    from presidio_analyzer.nlp_engine import NlpEngineProvider  # noqa: PLC0415

    available = _get_available_lang_codes()
    models_config = [
        {"lang_code": code, "model_name": LANGUAGE_MODELS[code]}
        for code in available
        if code in LANGUAGE_MODELS
    ]

    provider = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": models_config,
    })
    nlp_engine = provider.create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=available)

    # Built-in country/industry recognizers + user-defined custom patterns
    all_recognizer_defs = CUSTOM_RECOGNIZER_DEFS + _cp.as_recognizer_defs()
    for defn in all_recognizer_defs:
        patterns = [Pattern(f"{defn['entity']}_PATTERN", p, defn["score"]) for p in defn["patterns"]]
        for lang in ({"en"} | ({defn["native_lang"]} if defn["native_lang"] in available else set())):
            analyzer.registry.add_recognizer(
                PatternRecognizer(
                    supported_entity=defn["entity"],
                    patterns=patterns,
                    context=defn["context"],
                    supported_language=lang,
                )
            )

    return analyzer


def _get_engines():
    global _analyzer, _anonymizer
    if _analyzer is None:
        from presidio_anonymizer import AnonymizerEngine  # noqa: PLC0415

        _analyzer = _build_analyzer()
        _anonymizer = AnonymizerEngine()
    return _analyzer, _anonymizer


# ── Public API ─────────────────────────────────────────────────────────────────

def get_supported_entities() -> list[dict]:
    custom = [
        {"id": p["entity_type"], "label": p["label"], "description": p.get("description", p["label"])}
        for p in _cp.get_all_patterns()
        if not any(e["id"] == p["entity_type"] for e in SUPPORTED_ENTITIES)
    ]
    return SUPPORTED_ENTITIES + custom


def get_supported_languages() -> list[dict]:
    available = _get_available_lang_codes()
    return [
        {"code": code, "label": LANGUAGE_LABELS.get(code, code), "installed": code in available}
        for code in LANGUAGE_LABELS
    ]


def detect_language(text: str) -> str:
    """Return ISO 639-1 code for *text*, falling back to 'en' on failure."""
    try:
        from langdetect import detect  # noqa: PLC0415

        lang = detect(text[:3000])
        return lang if lang in LANGUAGE_MODELS else "en"
    except Exception:
        return "en"


def redact_text(
    text: str,
    language: str = "auto",
    entities: Optional[list[str]] = None,
    operator: str = "replace",
) -> dict:
    """
    Detect and anonymize PII in *text*.

    Returns:
        {redacted_text, entities_found, entity_counts, detected_language}
    """
    from presidio_anonymizer.entities import OperatorConfig  # noqa: PLC0415

    detected = detect_language(text) if (language == "auto" or not language) else language
    available = _get_available_lang_codes()
    analysis_lang = detected if detected in available else "en"

    logger.info(
        "Redacting | lang=%s (analysis=%s) | operator=%s | chars=%d",
        detected,
        analysis_lang,
        operator,
        len(text),
    )

    try:
        analyzer, anonymizer = _get_engines()
        entity_types = entities or [e["id"] for e in SUPPORTED_ENTITIES]
        results = analyzer.analyze(text=text, language=analysis_lang, entities=entity_types)

        def _make_config(op: str) -> OperatorConfig:
            if op == "mask":
                return OperatorConfig("mask", {"masking_char": "*", "chars_to_mask": 100, "from_end": False})
            if op == "hash":
                return OperatorConfig("hash", {"hash_type": "sha256"})
            return OperatorConfig(op)

        anonymized = anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators={r.entity_type: _make_config(operator) for r in results},
        )
    except Exception as exc:
        raise RedactionError(f"Presidio analysis failed: {exc}") from exc

    findings = [
        {"type": r.entity_type, "start": r.start, "end": r.end,
         "score": round(r.score, 2), "original": text[r.start:r.end]}
        for r in sorted(results, key=lambda x: x.start)
    ]

    return {
        "redacted_text": anonymized.text,
        "entities_found": findings,
        "entity_counts": dict(Counter(f["type"] for f in findings)),
        "detected_language": detected,
    }
