import asyncio
import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request

app = FastAPI(title="Deterministic Demo AI Provider", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "provider": "deterministic-demo-only"}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> dict[str, Any]:
    expected = os.environ.get("DEMO_AI_TOKEN", "")
    if not expected or request.headers.get("Authorization") != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid demo provider token")
    body = await request.json()
    messages = body.get("messages") if isinstance(body, dict) else None
    if not isinstance(messages, list):
        raise HTTPException(status_code=422, detail="messages are required")
    user_text = next(
        (
            item.get("content", "")
            for item in reversed(messages)
            if isinstance(item, dict) and item.get("role") == "user"
        ),
        "",
    )
    if "[demo-ai-timeout]" in str(user_text).casefold():
        await asyncio.sleep(float(os.environ.get("DEMO_AI_TIMEOUT_SECONDS", "3")))
    lower = str(user_text).casefold()
    service_type = (
        "furnace_service"
        if "furnace" in lower or "heat" in lower
        else "air_conditioning_service"
        if "air condition" in lower or " ac " in f" {lower} "
        else "unknown"
    )
    extracted = {
        "service_type": service_type,
        "location": "Surrey" if "surrey" in lower else None,
        "preferred_time": "Tuesday afternoon" if "tuesday" in lower else None,
        "urgency": "high" if "stopped" in lower or "urgent" in lower else "medium",
        "summary": "Synthetic HVAC enquiry parsed by the deterministic demo provider.",
    }
    return {
        "id": "demo_completion",
        "object": "chat.completion",
        "choices": [{"message": {"role": "assistant", "content": json.dumps(extracted)}}],
    }
