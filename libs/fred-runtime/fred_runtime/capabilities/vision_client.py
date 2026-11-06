# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Capability-facing client for Knowledge Flow's configured vision model."""

from __future__ import annotations

import httpx


class VisionServiceUnavailable(Exception):
    """A bounded vision call could not return a usable answer."""


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
