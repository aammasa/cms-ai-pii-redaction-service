"""AI chat endpoint — Azure OpenAI with in-process MCP tool calls."""

import asyncio
import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from openai import AzureOpenAI
from pydantic import BaseModel

# ── In-process MCP tool registry ──────────────────────────────────────────────
# Import mcp instance + tool modules (side-effects register @mcp.tool decorators)
from mcp_server.app import mcp  # noqa: E402
from mcp_server.tools import patterns as _patterns_mod  # noqa: F401
from mcp_server.tools import redact as _redact_mod      # noqa: F401
from mcp_server.tools import summarize as _summarize_mod  # noqa: F401

# ── OpenAI client (lazy) ───────────────────────────────────────────────────────

_openai_client: "AzureOpenAI | None" = None


def _get_openai_client() -> "AzureOpenAI":
    global _openai_client
    if _openai_client is None:
        _openai_client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/"),
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version="2024-12-01-preview",
        )
    return _openai_client


router = APIRouter()


# ── Request / response models ─────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    document_context: str | None = None


class ChatResponse(BaseModel):
    reply: str


# ── In-process tool helpers ───────────────────────────────────────────────────

def _get_tool_schemas() -> list[dict]:
    """Return OpenAI function-calling schemas for all registered MCP tools."""
    schemas = []
    for tool in mcp._tool_manager.list_tools():
        schemas.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.parameters,
            },
        })
    return schemas


async def _call_tool(name: str, arguments: dict) -> Any:
    """Dispatch a tool call in-process (runs sync tool fns in a thread)."""
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    tool = tools.get(name)
    if tool is None:
        return f"Unknown tool: {name}"
    try:
        if asyncio.iscoroutinefunction(tool.fn):
            result = await tool.fn(**arguments)
        else:
            result = await asyncio.to_thread(tool.fn, **arguments)
        return json.dumps(result) if isinstance(result, dict) else str(result)
    except Exception as exc:
        return f"Tool error: {exc}"


# ── Chat endpoint ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are PII Assistant, a helpful AI embedded in the Trimble PII Redaction & Summarization tool.
You have tools to list entities/languages/patterns, redact text, summarize redacted text, and manage custom patterns.
Be concise and professional. Use tools when the user's question can be answered by them."""


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    try:
        tool_schemas = _get_tool_schemas()
        oai = _get_openai_client()
        deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1")
    except KeyError as exc:
        raise HTTPException(status_code=500, detail=f"Missing env var: {exc}") from exc

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if req.document_context:
        messages.append({"role": "system", "content": f"Document context:\n{req.document_context}"})
    for h in req.history:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": req.message})

    for _ in range(8):
        response = oai.chat.completions.create(
            model=deployment,
            messages=messages,
            tools=tool_schemas or None,
            tool_choice="auto" if tool_schemas else "none",
            temperature=0.3,
            max_tokens=1024,
        )
        choice = response.choices[0]

        if choice.finish_reason == "tool_calls":
            messages.append(choice.message.model_dump())
            for tc in choice.message.tool_calls:
                fn_args = json.loads(tc.function.arguments or "{}")
                result = await _call_tool(tc.function.name, fn_args)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)})
        else:
            return ChatResponse(reply=(choice.message.content or "").strip())

    return ChatResponse(reply="Reached max tool calls. Try a more specific question.")
