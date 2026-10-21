from __future__ import annotations

import httpx
import pytest

from control_plane_backend.product import service as product_service


@pytest.mark.asyncio
async def test_model_metadata_is_projected_from_pod(monkeypatch) -> None:
    real_client = httpx.AsyncClient

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://pod/agents/models-catalog"
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "id": "model__openai__discovered.gateway.abc",
                        "provider": "openai",
                        "name": "chat-a",
                        "display_name": "Chat A",
                        "profile_ids": ["discovered.chat.gateway.abc"],
                        "chat_profile_ids": ["discovered.chat.gateway.abc"],
                        "context_window_tokens": 32768,
                        "max_input_tokens": 30000,
                        "max_output_tokens": 2048,
                    },
                    {
                        "id": "model__openai__discovered.gateway.def",
                        "provider": "openai",
                        "name": "chat-b",
                        "context_window_tokens": "invalid",
                        "max_input_tokens": 0,
                    },
                ]
            },
        )

    monkeypatch.setattr(
        product_service.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    catalog = await product_service._model_capabilities_for_source_uncached("http://pod")

    assert catalog is not None
    first, second = catalog.entries
    assert first.model_display_name == "Chat A"
    assert first.model_context_window_tokens == 32768
    assert first.model_max_input_tokens == 30000
    assert first.model_max_output_tokens == 2048
    assert second.model_context_window_tokens is None
    assert second.model_max_input_tokens is None
    assert second.model_max_output_tokens is None
