"""Summarization service — sends PII-free text to Claude. No PII ever reaches the LLM."""

import logging
import os

from ..constants import ENV_ANTHROPIC_API_KEY, LLM_MODEL
from ..errors.exceptions import SummarizationError

logger = logging.getLogger(__name__)

_LENGTH_MAP: dict[str, str] = {
    "short":    "2–3 concise sentences",
    "medium":   "a clear paragraph (4–6 sentences)",
    "detailed": "3–4 structured paragraphs covering all key points",
}


def summarize_text(redacted_text: str, length: str = "short") -> str:
    """
    Summarize PII-free *redacted_text* using Claude.

    Falls back to a simple extractive summary if the Anthropic SDK is not
    installed or ``ANTHROPIC_API_KEY`` is not set.
    """
    instruction = _LENGTH_MAP.get(length, _LENGTH_MAP["short"])

    api_key = os.environ.get(ENV_ANTHROPIC_API_KEY)
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — using extractive fallback")
        return _extractive_summary(redacted_text, length)

    try:
        import anthropic  # noqa: PLC0415

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Summarize the following text in {instruction}. "
                        "Focus on key facts and meaning. "
                        "Note: some values appear as placeholders like <PERSON> or <EMAIL_ADDRESS> "
                        "because PII has been redacted — treat them naturally.\n\n"
                        f"{redacted_text}"
                    ),
                }
            ],
        )
        logger.info("Summarization complete | model=%s | length=%s", LLM_MODEL, length)
        return response.content[0].text.strip()

    except ImportError:
        logger.warning("anthropic package not installed — using extractive fallback")
        return _extractive_summary(redacted_text, length)
    except Exception as exc:
        raise SummarizationError(f"Claude API call failed: {exc}") from exc


def _extractive_summary(text: str, length: str) -> str:
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
    n = {"short": 2, "medium": 4, "detailed": 8}.get(length, 2)
    return ". ".join(sentences[:n]) + ("." if sentences else "")
