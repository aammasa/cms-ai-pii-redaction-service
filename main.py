"""
Backward-compatibility shim.

Preferred entry point (per CLAUDE.md):
    uvicorn src.api:api --host 0.0.0.0 --port 8000

This file exists so that the old command still works:
    uvicorn main:app --port 8000
"""

from src.api import api as app  # noqa: F401
