# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Capability-facing client for Knowledge Flow's configured vision model."""

from __future__ import annotations

import httpx

from fred_runtime.common.outbound_credentials import static_person_provider


class VisionServiceUnavailable(Exception):
    """A bounded vision call could not return a usable answer."""


class SaveVisionAvailabilityClient:
    """Check Knowledge Flow with the saving user's token and a shared HTTP pool."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        knowledge_flow_url: str,
        access_token: str | None,
    ) -> None:
        self._client = client
        self._url = knowledge_flow_url.rstrip("/") + "/vision/availability"
        self._credentials = static_person_provider(access_token)

    async def available(self) -> bool:
        try:
            authorization = (await self._credentials.credentials()).authorization
            response = await self._client.get(
                self._url,
                headers={"Authorization": authorization} if authorization else None,
                timeout=3.0,
            )
            response.raise_for_status()
            return response.json().get("available") is True
        except (httpx.HTTPError, ValueError, TypeError):
            return False


class KnowledgeFlowVisionClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def available(self) -> bool:
        try:
            response = await self._client.get("/vision/availability")
            response.raise_for_status()
            return response.json().get("available") is True
        except (httpx.HTTPError, ValueError, TypeError):
            return False

    async def describe(self, image: bytes, prompt: str) -> str:
        if len(image) > 4 * 1024 * 1024 or len(prompt) > 16_000:
            raise ValueError("Vision input exceeds the service limit")
        try:
            response = await self._client.post(
                "/internal/vision/describe",
                data={"prompt": prompt},
                files={"image": ("slide.png", image, "image/png")},
            )
            response.raise_for_status()
            answer = response.json().get("text")
            if not isinstance(answer, str) or not answer:
                raise ValueError("Empty vision answer")
            return answer
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise VisionServiceUnavailable("Vision service unavailable") from exc
