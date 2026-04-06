"""Summarization route — /summarize. HTTP handling only."""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from ..constants import DEFAULT_API_KEY_HEADER, ENV_API_KEY_HEADER, LLM_MODEL
from ..models import SummarizeRequest, SummarizeResponse
from ..summarization.summarizer import summarize_text
from ..util.auth import verify_api_key
from ..util.quota import check_summarize_quota, quota_headers, record_summarize_call
from ..util.rate_limit import LIMIT_SUMMARIZE, get_team_config, limiter

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _api_key(request: Request) -> str:
    header_name = os.environ.get(ENV_API_KEY_HEADER, DEFAULT_API_KEY_HEADER)
    return request.headers.get(header_name, "").strip()


@router.post("/summarize", response_model=SummarizeResponse)
@limiter.limit(LIMIT_SUMMARIZE)
def summarize(req: SummarizeRequest, request: Request, response: Response) -> JSONResponse:
    """
    Summarize PII-free text via Claude.

    Enforces two limits:
      1. Hourly burst rate limit (slowapi) — prevents rapid-fire calls
      2. Daily LLM quota per team — controls Claude API cost

    Response headers:
      X-Quota-Summarize-Limit      total daily allowance for this key
      X-Quota-Summarize-Used       calls made today
      X-Quota-Summarize-Remaining  calls remaining today
      X-Quota-Reset                date quota resets (UTC)
    """
    api_key = _api_key(request)
    team_cfg = get_team_config(api_key)
    daily_limit = team_cfg.get("summarize_per_day", 50)

    # ── Daily LLM quota check ──────────────────────────────────────────────────
    allowed, used, limit = check_summarize_quota(api_key, daily_limit)
    if not allowed:
        headers = quota_headers(api_key, daily_limit)
        return JSONResponse(
            status_code=429,
            content={
                "detail": (
                    f"Daily summarize quota of {limit} calls exceeded. "
                    f"Quota resets at UTC midnight. "
                    f"Contact your administrator to increase your team's allowance."
                )
            },
            headers=headers,
        )

    # ── Call LLM ──────────────────────────────────────────────────────────────
    summary = summarize_text(req.redacted_text, req.length)
    record_summarize_call(api_key)

    logger.info(
        "summarize completed",
        extra={
            "event_type":        "summarize",
            "client_ip":         _client_ip(request),
            "session_id":        req.session_id,
            "text_length":       len(req.redacted_text),
            "summarization_run": True,
            "llm_model":         LLM_MODEL,
        },
    )

    # ── Return with quota headers so clients can self-throttle ────────────────
    headers = quota_headers(api_key, daily_limit)
    return JSONResponse(
        content={"summary": summary},
        headers=headers,
    )
