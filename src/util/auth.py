"""API key authentication dependency."""

import logging
import os

from fastapi import HTTPException, Request

from ..constants import DEFAULT_API_KEY_HEADER, ENV_API_KEY, ENV_API_KEY_HEADER

logger = logging.getLogger(__name__)


async def verify_api_key(request: Request) -> None:
    """
    FastAPI dependency injected on all routers.

    - If ``API_KEY`` env var is **not set**, auth is disabled (development mode).
    - If ``API_KEY`` is set, every request must include it in the header named
      by ``API_KEY_HEADER`` (default: ``X-API-Key``).
    """
    api_key = os.environ.get(ENV_API_KEY)
    if not api_key:
        return  # Dev mode — no auth required

    header_name = os.environ.get(ENV_API_KEY_HEADER, DEFAULT_API_KEY_HEADER)
    provided = request.headers.get(header_name)

    if provided != api_key:
        logger.warning("Unauthorized request | path=%s | ip=%s", request.url.path, request.client)
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
