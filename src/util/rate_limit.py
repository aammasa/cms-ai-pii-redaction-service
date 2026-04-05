"""
Rate limiting — per API key (falls back to IP when auth is disabled).

Uses slowapi (limits library) with in-memory storage by default.
Set REDIS_URL in .env to switch to a Redis backend for multi-pod deployments.

Per-team limits are loaded from quota_config.json at startup.
"""

import json
import logging
import os
from pathlib import Path

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..constants import ENV_API_KEY_HEADER, DEFAULT_API_KEY_HEADER

logger = logging.getLogger(__name__)

_QUOTA_CONFIG_PATH = Path(__file__).resolve().parents[2] / "quota_config.json"
_quota_config: dict | None = None


# ── Config loader ──────────────────────────────────────────────────────────────

def _load_quota_config() -> dict:
    global _quota_config
    if _quota_config is not None:
        return _quota_config
    try:
        with open(_QUOTA_CONFIG_PATH, "r") as f:
            _quota_config = json.load(f)
        logger.info("Quota config loaded from %s", _QUOTA_CONFIG_PATH)
    except FileNotFoundError:
        logger.warning("quota_config.json not found — using built-in defaults")
        _quota_config = {"default": {"requests_per_minute": 60, "process_per_hour": 30, "summarize_per_day": 50}, "teams": {}}
    return _quota_config


def get_team_config(api_key: str) -> dict:
    """Return the quota config for a given API key (falls back to default)."""
    config = _load_quota_config()
    return config["teams"].get(api_key, config["default"])


# ── Key function ───────────────────────────────────────────────────────────────

def rate_limit_key(request: Request) -> str:
    """
    Identify requests by API key when auth is enabled, IP address otherwise.
    This ensures per-team rate limits rather than global ones.
    """
    header_name = os.environ.get(ENV_API_KEY_HEADER, DEFAULT_API_KEY_HEADER)
    api_key = request.headers.get(header_name, "").strip()
    if api_key:
        return f"key:{api_key}"
    # Fallback: IP-based limiting when auth is disabled (dev mode)
    forwarded = request.headers.get("X-Forwarded-For")
    ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "unknown"
    )
    return f"ip:{ip}"


# ── Fixed limit strings ────────────────────────────────────────────────────────
# slowapi calls callable limits with NO arguments, so we use fixed strings.
# Per-team daily LLM quotas are enforced separately in src/util/quota.py.
# Each API key gets its own counter bucket via key_func — teams don't share limits.

LIMIT_GENERAL   = "60/minute"    # /redact   — general text redaction
LIMIT_PROCESS   = "30/hour"      # /process  — file upload + extraction
LIMIT_SUMMARIZE = "10/hour"      # /summarize — burst guard before daily quota check


# ── Limiter instance ───────────────────────────────────────────────────────────

def _make_storage_uri() -> str:
    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        logger.info("Rate limiter using Redis backend: %s", redis_url)
        return redis_url
    logger.info("Rate limiter using in-memory backend (set REDIS_URL for multi-pod deployments)")
    return "memory://"


limiter = Limiter(
    key_func=rate_limit_key,
    storage_uri=_make_storage_uri(),
    headers_enabled=True,   # adds X-RateLimit-* headers to responses
)

