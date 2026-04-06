"""Redaction routes — /redact and /process. HTTP handling only."""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Request, UploadFile
from starlette.responses import Response

from ..models import ProcessResponse, RedactRequest, RedactResponse
from ..redaction.extractor import extract_text
from ..redaction.redactor import redact_text
from ..util.auth import verify_api_key
from ..util.rate_limit import limiter, LIMIT_GENERAL, LIMIT_PROCESS

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/redact", response_model=RedactResponse)
@limiter.limit(LIMIT_GENERAL)
def redact(req: RedactRequest, request: Request, response: Response) -> RedactResponse:
    """Redact PII from raw text. Raises RedactionError on failure (handled globally)."""
    result = redact_text(
        text=req.text,
        language=req.language,
        entities=req.entities,
        operator=req.operator,
    )

    logger.info(
        "redact completed",
        extra={
            "event_type":        "redact",
            "client_ip":         _client_ip(request),
            "session_id":        req.session_id,
            "detected_language": result["detected_language"],
            "entity_counts":     result["entity_counts"],
            "pii_count":         len(result["entities_found"]),
            "operator":          req.operator,
            "text_length":       len(req.text),
        },
    )

    return RedactResponse(**result, original_text=req.text)


@router.post("/process", response_model=ProcessResponse)
@limiter.limit(LIMIT_PROCESS)
async def process_file(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    language: str = "auto",
    session_id: Optional[str] = None,
) -> ProcessResponse:
    """Upload a file, extract text, detect language, and redact PII."""
    sid       = session_id or str(uuid.uuid4())
    contents  = await file.read()
    filename  = file.filename or "upload"
    file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"

    # ExtractionError / RedactionError bubble up to global handlers
    text   = extract_text(contents, file_type)
    result = redact_text(text=text, language=language)

    logger.info(
        "process completed",
        extra={
            "event_type":        "process",
            "client_ip":         _client_ip(request),
            "session_id":        sid,
            "doc_filename":      filename,
            "file_type":         file_type,
            "detected_language": result["detected_language"],
            "entity_counts":     result["entity_counts"],
            "pii_count":         len(result["entities_found"]),
            "operator":          "replace",
            "text_length":       len(text),
        },
    )

    return ProcessResponse(
        **result,
        original_text=text,
        filename=filename,
        file_type=file_type,
        session_id=sid,
    )
