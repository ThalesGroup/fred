# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Capability-facing client for CP-admitted preparation text completion."""

from __future__ import annotations

import asyncio
import secrets

import httpx

from fred_runtime.common.outbound_credentials import DelegationRuntime


class TextServiceUnavailable(Exception):
    """A bounded text call could not return a usable answer."""


class KnowledgeFlowTextClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        url: str,
        preparation_id: str,
        credentials: DelegationRuntime,
    ) -> None:
        self._client = client
        self._url = url.rstrip("/") + "/internal/text/complete"
        self._preparation_id = preparation_id
        self._credentials = credentials

    async def complete(self, system: str, user: str) -> str:
        if not system or len(system) > 16_000 or not user or len(user) > 64_000:
            raise ValueError("Text input exceeds the service limit")
        lease = await self._credentials.workload_token_lease()
        if lease is None:
            raise TextServiceUnavailable("Preparation requires a workload identity")
        payload = {
            "system": system,
            "user": user,
            "preparation_id": self._preparation_id,
        }
        headers = {"Authorization": f"Bearer {lease.token}"}
        try:
            response = await self._client.post(
                self._url, json=payload, headers=headers, timeout=75.0
            )
            for attempt in range(3):
                if response.status_code != 429:
                    break
                await asyncio.sleep(0.25 * (2**attempt) + secrets.randbelow(200) / 1000)
                response = await self._client.post(
                    self._url, json=payload, headers=headers, timeout=75.0
                )
            response.raise_for_status()
            answer = response.json().get("text")
            if not isinstance(answer, str) or not answer or len(answer) > 32_000:
                raise ValueError("Invalid text answer")
            return answer
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise TextServiceUnavailable("Text service unavailable") from exc
