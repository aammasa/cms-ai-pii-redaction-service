"""Global FastAPI exception handlers — routers must not repeat try/except for these."""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from .exceptions import ExtractionError, RedactionError, SummarizationError

logger = logging.getLogger(__name__)


async def extraction_error_handler(request: Request, exc: ExtractionError) -> JSONResponse:
    logger.error("Extraction failed | path=%s | %s", request.url.path, exc)
    return JSONResponse(status_code=422, content={"detail": str(exc)})


async def redaction_error_handler(request: Request, exc: RedactionError) -> JSONResponse:
    logger.error("Redaction failed | path=%s | %s", request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


async def summarization_error_handler(request: Request, exc: SummarizationError) -> JSONResponse:
    logger.error("Summarization failed | path=%s | %s", request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


