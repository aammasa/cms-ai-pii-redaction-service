"""Health, entity catalogue, and language catalogue routes."""

from fastapi import APIRouter, Depends

from ..models import EntitiesResponse, LanguagesResponse
from ..redaction.redactor import get_supported_entities, get_supported_languages
from ..util.auth import verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/entities", response_model=EntitiesResponse)
def list_entities() -> EntitiesResponse:
    """Return all supported PII entity types including country-specific ones."""
    return EntitiesResponse(entities=get_supported_entities())


@router.get("/languages", response_model=LanguagesResponse)
def list_languages() -> LanguagesResponse:
    """Return all supported languages and whether their NLP model is installed."""
    return LanguagesResponse(languages=get_supported_languages())
