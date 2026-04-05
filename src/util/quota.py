"""
Daily LLM quota tracker — controls Claude API call costs per team.

Tracks summarize calls per API key per UTC day.
Storage: in-memory dict (dev) or Redis (production via REDIS_URL).

The quota resets automatically at UTC midnight — no cron job needed
because counters are keyed by date string.

Response headers added on every summarize call:
  X-Quota-Summarize-Limit:     50
  X-Quota-Summarize-Used:      12
  X-Quota-Summarize-Remaining: 38
  X-Quota-Reset:               2026-04-06 (next UTC day)
"""

import logging
import os
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)

# ── In-memory store ────────────────────────────────────────────────────────────
# Structure: { "key:team-key:2026-04-05": 12, ... }
_memory_store: dict[str, int] = {}
_lock = Lock()


# ── Storage helpers ────────────────────────────────────────────────────────────

def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _tomorrow() -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")


def _store_key(api_key: str) -> str:
    return f"quota:summarize:{api_key}:{_today()}"


def _redis_client():
    """Return a Redis client if REDIS_URL is set, otherwise None."""
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        return None
    try:
        import redis  # noqa: PLC0415
        return redis.from_url(redis_url, decode_responses=True)
    except ImportError:
        logger.warning("redis package not installed — quota tracking uses in-memory store")
        return None
    except Exception as exc:
        logger.warning("Redis connection failed (%s) — falling back to in-memory", exc)
        return None


def _get_count(store_key: str) -> int:
    r = _redis_client()
    if r:
        val = r.get(store_key)
        return int(val) if val else 0
    with _lock:
        return _memory_store.get(store_key, 0)


def _increment(store_key: str) -> int:
    """Increment counter and return new value. Sets TTL of 48h on Redis keys."""
    r = _redis_client()
    if r:
        pipe = r.pipeline()
        pipe.incr(store_key)
        pipe.expire(store_key, 172800)  # 48 hours TTL
        results = pipe.execute()
        return results[0]
    with _lock:
        _memory_store[store_key] = _memory_store.get(store_key, 0) + 1
        return _memory_store[store_key]


# ── Public API ─────────────────────────────────────────────────────────────────

def check_summarize_quota(api_key: str, daily_limit: int) -> tuple[bool, int, int]:
    """
    Check whether the key has remaining daily summarize quota.

    Returns:
        (allowed: bool, used: int, limit: int)
    """
    store_key = _store_key(api_key or "anonymous")
    used = _get_count(store_key)
    allowed = used < daily_limit
    if not allowed:
        logger.warning(
            "Summarize quota exceeded | key=%s | used=%d | limit=%d",
            api_key[:8] + "…" if len(api_key) > 8 else api_key,
            used, daily_limit,
        )
    return allowed, used, daily_limit


def record_summarize_call(api_key: str) -> int:
    """Increment the summarize counter for today. Returns new count."""
    store_key = _store_key(api_key or "anonymous")
    count = _increment(store_key)
    logger.info("Summarize quota used | key=…%s | today=%d", api_key[-4:], count)
    return count


def quota_headers(api_key: str, daily_limit: int) -> dict[str, str]:
    """
    Return HTTP headers describing quota state for this key.
    Attach these to summarize responses so clients can self-throttle.
    """
    store_key = _store_key(api_key or "anonymous")
    used = _get_count(store_key)
    remaining = max(0, daily_limit - used)
    return {
        "X-Quota-Summarize-Limit":     str(daily_limit),
        "X-Quota-Summarize-Used":      str(used),
        "X-Quota-Summarize-Remaining": str(remaining),
        "X-Quota-Reset":               _tomorrow(),
    }
