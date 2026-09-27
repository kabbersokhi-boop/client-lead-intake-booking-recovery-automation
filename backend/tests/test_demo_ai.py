import json
from asyncio import run

import pytest
from fastapi import HTTPException

from demo_ai.main import chat_completions, health


class DemoRequest:
    def __init__(self, token: str | None, body: dict):
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.body = body

    async def json(self) -> dict:
        return self.body


def test_deterministic_demo_provider_is_labeled_and_returns_schema(monkeypatch):
    monkeypatch.setenv("DEMO_AI_TOKEN", "test-demo-token")
    assert health() == {
        "status": "ok",
        "provider": "deterministic-demo-only",
    }

    response = run(
        chat_completions(
            DemoRequest(
                "test-demo-token",
                {
            "messages": [
                {
                    "role": "user",
                    "content": "The furnace stopped heating in Surrey on Tuesday.",
                }
            ]
                },
            )
        )
    )
    extracted = json.loads(response["choices"][0]["message"]["content"])
    assert extracted == {
        "service_type": "furnace_service",
        "location": "Surrey",
        "preferred_time": "Tuesday afternoon",
        "urgency": "high",
        "summary": "Synthetic HVAC enquiry parsed by the deterministic demo provider.",
    }


def test_deterministic_demo_provider_requires_its_local_token(monkeypatch):
    monkeypatch.setenv("DEMO_AI_TOKEN", "test-demo-token")
    with pytest.raises(HTTPException) as raised:
        run(
            chat_completions(
                DemoRequest(
                    None,
                    {"messages": [{"role": "user", "content": "furnace"}]},
                )
            )
        )
    assert raised.value.status_code == 401
