# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Capability-facing client for Knowledge Flow's configured text model."""

from __future__ import annotations

import asyncio
import random

import httpx


class TextServiceUnavailable(Exception):
    """A bounded text call could not return a usable answer."""


class KnowledgeFlowTextClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def complete(self, system: str, user: str) -> str:
        if not system or len(system) > 16_000 or not user or len(user) > 64_000:
            raise ValueError("Text input exceeds the service limit")
        try:
            for attempt in range(4):
                response = await self._client.post(
                    "/internal/text/complete", json={"system": system, "user": user}
                )
                if response.status_code != 429 or attempt == 3:
                    break
                await asyncio.sleep(0.25 * (2**attempt) + random.uniform(0, 0.2))
            response.raise_for_status()
            answer = response.json().get("text")
            if not isinstance(answer, str) or not answer or len(answer) > 32_000:
                raise ValueError("Invalid text answer")
            return answer
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise TextServiceUnavailable("Text service unavailable") from exc
