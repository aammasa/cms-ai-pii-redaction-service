"""Domain exceptions for the PII Redaction service."""


class PIIRedactionBaseError(Exception):
    """Base exception for all service errors."""


class ExtractionError(PIIRedactionBaseError):
    """Raised when text extraction from a document fails."""


class UnsupportedFileTypeError(ExtractionError):
    """Raised when the file type is not supported for extraction."""


class RedactionError(PIIRedactionBaseError):
    """Raised when Presidio PII analysis or anonymization fails."""


class SummarizationError(PIIRedactionBaseError):
    """Raised when Claude summarization fails."""


class AuditError(PIIRedactionBaseError):
    """Raised when writing or reading the audit log fails."""
