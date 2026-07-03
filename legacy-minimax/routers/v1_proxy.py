"""
OpenAI-compatible /v1 proxy endpoint for tools like deepseek-tui.
Proxies standard Chat Completions requests through the configured provider.
"""

import json
import time
from typing import Optional, List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.config import load_config

router = APIRouter(prefix="/v1")


class ChatMessage(BaseModel):
    role: str
    content: Optional[str] = None
    name: Optional[str] = None
    tool_calls: Optional[list] = None
    tool_call_id: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 32768
    stream: Optional[bool] = False
    tools: Optional[list] = None


@router.post("/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    """OpenAI-compatible Chat Completions endpoint."""

    cfg = load_config()
    api_key = cfg.get("api_key", "")
    base_url = cfg.get("base_url", "https://api.minimaxi.com/v1")
    # deepseek-tui hardcodes its own model names; always map to the configured backend model
    model = cfg.get("model", "MiniMax-M2.7-HighSpeed")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    messages = [
        {"role": m.role, "content": m.content}
        for m in req.messages
        if m.content is not None or m.role == "assistant"
    ]

    if req.stream:
        async def generate():
            try:
                stream = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=max(req.temperature or 0.7, 0.3),
                    max_tokens=req.max_tokens or 32768,
                    stream=True,
                )
                async for chunk in stream:
                    data = chunk.model_dump_json()
                    yield f"data: {data}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    else:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=max(req.temperature or 0.7, 0.3),
            max_tokens=req.max_tokens or 32768,
        )
        return resp.model_dump()


@router.get("/models")
async def list_models():
    """List available models."""
    cfg = load_config()
    return {
        "object": "list",
        "data": [
            {
                "id": cfg.get("model", "MiniMax-M2.7-HighSpeed"),
                "object": "model",
                "created": int(time.time()),
                "owned_by": "1052",
            }
        ],
    }
