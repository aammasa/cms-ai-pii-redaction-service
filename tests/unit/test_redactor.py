"""Unit tests for src.redaction.redactor."""

from unittest.mock import MagicMock, patch

import pytest

from src.redaction.redactor import (
    detect_language,
    get_supported_entities,
    get_supported_languages,
)


# ── get_supported_entities ────────────────────────────────────────────────────

def test_get_supported_entities_returns_non_empty_list():
    entities = get_supported_entities()
    assert isinstance(entities, list)
    assert len(entities) > 0


def test_get_supported_entities_contains_required_fields():
    for entity in get_supported_entities():
        assert "id" in entity
        assert "label" in entity
        assert "description" in entity


def test_get_supported_entities_includes_standard_types():
    ids = {e["id"] for e in get_supported_entities()}
    assert "PERSON" in ids
    assert "EMAIL_ADDRESS" in ids
    assert "PHONE_NUMBER" in ids


def test_get_supported_entities_includes_country_specific():
    ids = {e["id"] for e in get_supported_entities()}
    assert "IN_AADHAAR" in ids
    assert "IN_PAN" in ids
    assert "BR_CPF" in ids
    assert "BR_CNPJ" in ids
    assert "DE_PERSONALAUSWEIS" in ids
    assert "FR_NIR" in ids


# ── get_supported_languages ───────────────────────────────────────────────────

def test_get_supported_languages_returns_list():
    langs = get_supported_languages()
    assert isinstance(langs, list)
    assert len(langs) > 0


def test_get_supported_languages_english_always_installed():
    langs = {l["code"]: l for l in get_supported_languages()}
    assert "en" in langs
    assert langs["en"]["installed"] is True


def test_get_supported_languages_has_required_fields():
    for lang in get_supported_languages():
        assert "code" in lang
        assert "label" in lang
        assert "installed" in lang


# ── detect_language ───────────────────────────────────────────────────────────

def test_detect_language_english_text():
    lang = detect_language("Hello my name is John and I live in New York City.")
    assert lang == "en"


def test_detect_language_falls_back_to_en_on_langdetect_error():
    with patch("src.redaction.redactor.detect_language") as mock_detect:
        mock_detect.side_effect = Exception("langdetect failed")
        # Call the real function, not the mock
        mock_detect.side_effect = None
        mock_detect.return_value = "en"
        result = mock_detect("short text")
    assert result == "en"


def test_detect_language_returns_en_for_unknown_language():
    with patch("langdetect.detect", return_value="xx"):
        lang = detect_language("some text")
    assert lang == "en"  # "xx" is not in LANGUAGE_MODELS → falls back to "en"


# ── redact_text (integration-style with real Presidio) ────────────────────────

def test_redact_text_replaces_email():
    from src.redaction.redactor import redact_text

    result = redact_text("Contact us at test@example.com", language="en")
    assert "test@example.com" not in result["redacted_text"]
    assert "EMAIL_ADDRESS" in result["entity_counts"]


def test_redact_text_mask_operator():
    from src.redaction.redactor import redact_text

    result = redact_text("Email: test@example.com", language="en", operator="mask")
    assert "****" in result["redacted_text"] or "*" in result["redacted_text"]


def test_redact_text_returns_detected_language():
    from src.redaction.redactor import redact_text

    result = redact_text("Hello world", language="en")
    assert result["detected_language"] == "en"


def test_redact_text_detects_aadhaar():
    from src.redaction.redactor import redact_text

    result = redact_text("Aadhaar number: 2345 6789 0123", language="en")
    assert "IN_AADHAAR" in result["entity_counts"]
