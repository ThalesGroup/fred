"""The preparation worker uses only Knowledge Flow's configured vision endpoint."""

import httpx
import pytest

from fred_runtime.capabilities.vision_client import (
    KnowledgeFlowVisionClient,
    SaveVisionAvailabilityClient,
    VisionServiceUnavailable,
)


@pytest.mark.asyncio
async def test_vision_client_sends_image_and_prompt_without_model_choice() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/vision/availability"):
            return httpx.Response(200, json={"available": True})
        return httpx.Response(200, json={"text": "slot 1"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://knowledge-flow/knowledge-flow/v1",
    ) as http_client:
        vision = KnowledgeFlowVisionClient(http_client)
        assert await vision.available()
        assert await vision.describe(b"image", "Read numbered slots") == "slot 1"
    assert requests[1].url.path == "/knowledge-flow/v1/internal/vision/describe"
    assert b"Read numbered slots" in requests[1].content
    assert b"image" in requests[1].content
    assert b"model" not in requests[1].content


@pytest.mark.asyncio
async def test_vision_client_reports_service_outage_safely() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
        base_url="http://knowledge-flow/knowledge-flow/v1",
    ) as http_client:
        vision = KnowledgeFlowVisionClient(http_client)
        assert not await vision.available()
        with pytest.raises(
            VisionServiceUnavailable, match="Vision service unavailable"
        ):
            await vision.describe(b"image", "Read")


@pytest.mark.asyncio
async def test_save_availability_uses_user_token_without_model_choice() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"available": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        availability = SaveVisionAvailabilityClient(
            client, "http://knowledge-flow/knowledge-flow/v1", "user-token"
        )
        assert await availability.available()
        assert await SaveVisionAvailabilityClient(
            client, "http://knowledge-flow/knowledge-flow/v1", None
        ).available()
    assert len(requests) == 2
    assert requests[0].url.path == "/knowledge-flow/v1/vision/availability"
    assert requests[0].headers["Authorization"] == "Bearer user-token"
    assert "Authorization" not in requests[1].headers
