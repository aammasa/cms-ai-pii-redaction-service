"""
Structured logging setup with Azure Log Analytics Workspace export.

Usage
-----
Call ``configure_logging()`` once at application startup (``src/api.py``).
Everywhere else use the standard logging API:

    import logging
    logger = logging.getLogger(__name__)

    logger.info("trace message", extra={
        "event_type": "process",
        "client_ip":  "10.0.0.1",
        ...
    })

Azure destination
-----------------
Set ``AZURE_LOG_WORKSPACE_ID`` and ``AZURE_LOG_WORKSPACE_KEY`` in the
environment (or .env).  When absent the handler is skipped and logs only
go to stdout — no errors are raised.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

from ..constants import (
    DEFAULT_AZURE_LOG_TYPE,
    ENV_AZURE_LOG_TYPE,
    ENV_AZURE_LOG_WORKSPACE_ID,
    ENV_AZURE_LOG_WORKSPACE_KEY,
)

# Structured fields emitted on every trace record
TRACE_FIELDS = (
    "event_type",
    "client_ip",
    "session_id",
    "doc_filename",   # "filename" is reserved by logging.LogRecord
    "file_type",
    "detected_language",
    "entity_counts",
    "pii_count",
    "operator",
    "text_length",
    "summarization_run",
    "llm_model",
)


class AzureLogAnalyticsHandler(logging.Handler):
    """
    Sends log records to Azure Log Analytics Workspace via the
    HTTP Data Collector API (POST to the ODS ingestion endpoint).

    Failures are silently swallowed (``handleError``) so a Log Analytics
    outage never crashes the API.
    """

    def __init__(self, workspace_id: str, workspace_key: str, log_type: str) -> None:
        super().__init__()
        self._workspace_id = workspace_id
        self._workspace_key = workspace_key
        self._log_type = log_type
        self._url = (
            f"https://{workspace_id}.ods.opinsights.azure.com"
            "/api/logs?api-version=2016-04-01"
        )

    # ── HMAC-SHA256 signature required by the Data Collector API ──────────────

    def _signature(self, date: str, content_length: int) -> str:
        string_to_sign = (
            f"POST\n{content_length}\napplication/json\n"
            f"x-ms-date:{date}\n/api/logs"
        )
        decoded_key = base64.b64decode(self._workspace_key)
        digest = hmac.new(decoded_key, string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        encoded = base64.b64encode(digest).decode("utf-8")
        return f"SharedKey {self._workspace_id}:{encoded}"

    # ── Handler interface ─────────────────────────────────────────────────────

    def emit(self, record: logging.LogRecord) -> None:
        try:
            body = self._build_body(record)
            payload = json.dumps([body]).encode("utf-8")
            date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")

            with httpx.Client(timeout=5.0) as client:
                client.post(
                    self._url,
                    content=payload,
                    headers={
                        "Content-Type":  "application/json",
                        "Authorization": self._signature(date, len(payload)),
                        "Log-Type":      self._log_type,
                        "x-ms-date":     date,
                    },
                )
        except Exception:
            self.handleError(record)

    def _build_body(self, record: logging.LogRecord) -> dict:
        body: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.getMessage(),
        }
        for field in TRACE_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                # Strip the internal "doc_" prefix before sending to Log Analytics
                key = field[4:] if field.startswith("doc_") else field
                body[key] = value
        return body


# ── Public setup function ──────────────────────────────────────────────────────

def configure_logging() -> None:
    """
    Configure root logger.

    - Always: StreamHandler (stdout) with a human-readable format.
    - When Azure env vars are set: AzureLogAnalyticsHandler for structured
      trace records.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Console handler — human-readable for local dev / container stdout
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s  %(message)s")
        )
        root.addHandler(stream_handler)

    # Azure Log Analytics handler — only when credentials are configured
    workspace_id  = os.environ.get(ENV_AZURE_LOG_WORKSPACE_ID)
    workspace_key = os.environ.get(ENV_AZURE_LOG_WORKSPACE_KEY)

    if workspace_id and workspace_key:
        log_type = os.environ.get(ENV_AZURE_LOG_TYPE, DEFAULT_AZURE_LOG_TYPE)
        azure_handler = AzureLogAnalyticsHandler(workspace_id, workspace_key, log_type)
        azure_handler.setLevel(logging.INFO)
        root.addHandler(azure_handler)
        logging.getLogger(__name__).info(
            "Azure Log Analytics handler registered | workspace=%s | log_type=%s",
            workspace_id,
            log_type,
        )
    else:
        logging.getLogger(__name__).warning(
            "AZURE_LOG_WORKSPACE_ID / AZURE_LOG_WORKSPACE_KEY not set — "
            "traces will only appear in stdout"
        )
