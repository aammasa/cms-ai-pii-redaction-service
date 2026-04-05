"""Text extraction service. Supports: .txt, .pdf, .docx, .csv, .md"""

import csv
import io
import logging

from ..constants import SUPPORTED_FILE_TYPES
from ..errors.exceptions import ExtractionError, UnsupportedFileTypeError

logger = logging.getLogger(__name__)


def extract_text(contents: bytes, file_type: str) -> str:
    """Extract plain text from *contents* based on *file_type* extension."""
    fmt = file_type.lower().strip(".")
    logger.info("Extracting text | format=%s | bytes=%d", fmt, len(contents))

    if fmt in ("txt", "md"):
        return _extract_txt(contents)
    if fmt == "pdf":
        return _extract_pdf(contents)
    if fmt in ("docx", "doc"):
        return _extract_docx(contents)
    if fmt == "csv":
        return _extract_csv(contents)
    if fmt not in SUPPORTED_FILE_TYPES:
        raise UnsupportedFileTypeError(
            f"Unsupported file type: .{fmt}. "
            f"Supported: {', '.join(sorted(SUPPORTED_FILE_TYPES))}"
        )

    # Last-resort UTF-8 decode for any other accepted type
    try:
        return contents.decode("utf-8", errors="replace")
    except Exception as exc:
        raise ExtractionError(f"Could not decode file as UTF-8: {exc}") from exc


def _extract_txt(contents: bytes) -> str:
    return contents.decode("utf-8", errors="replace")


def _extract_pdf(contents: bytes) -> str:
    try:
        import pdfplumber
    except ImportError as exc:
        raise ExtractionError(
            "pdfplumber is required for PDF extraction. Run: pip install pdfplumber"
        ) from exc

    try:
        with pdfplumber.open(io.BytesIO(contents)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n\n".join(p for p in pages if p.strip())
    except Exception as exc:
        raise ExtractionError(f"PDF extraction failed: {exc}") from exc


def _extract_docx(contents: bytes) -> str:
    try:
        import docx
    except ImportError as exc:
        raise ExtractionError(
            "python-docx is required for DOCX extraction. Run: pip install python-docx"
        ) from exc

    try:
        doc = docx.Document(io.BytesIO(contents))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as exc:
        raise ExtractionError(f"DOCX extraction failed: {exc}") from exc


def _extract_csv(contents: bytes) -> str:
    text = contents.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = [" | ".join(row) for row in reader]
    return "\n".join(rows)
