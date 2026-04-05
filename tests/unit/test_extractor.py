"""Unit tests for src.redaction.extractor."""

import pytest

from src.errors.exceptions import UnsupportedFileTypeError
from src.redaction.extractor import extract_text
from tests.utils.mock_data import SAMPLE_CSV_BYTES, SAMPLE_TXT_BYTES


def test_extract_text_txt_returns_string():
    result = extract_text(SAMPLE_TXT_BYTES, "txt")
    assert isinstance(result, str)
    assert "John Smith" in result


def test_extract_text_md_same_as_txt():
    result = extract_text(b"# Heading\nSome content.", "md")
    assert "Heading" in result


def test_extract_text_csv_joins_fields():
    result = extract_text(SAMPLE_CSV_BYTES, "csv")
    assert "name" in result
    assert "email" in result
    assert "|" in result  # fields separated by " | "


def test_extract_text_unsupported_raises():
    with pytest.raises(UnsupportedFileTypeError):
        extract_text(b"data", "xyz")


def test_extract_text_strips_leading_dot_from_extension():
    result = extract_text(SAMPLE_TXT_BYTES, ".txt")
    assert isinstance(result, str)


def test_extract_text_empty_bytes_returns_empty_string():
    result = extract_text(b"", "txt")
    assert result == ""
