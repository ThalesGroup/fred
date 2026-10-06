# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Erase restricted web activity before deleting the identity-provider account."""

from __future__ import annotations

import asyncio
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from control_plane_backend.config.models import Configuration


async def erase_web_research_activity(
    config: Configuration,
    client: httpx.AsyncClient | None,
    user_id: str,
    authorization: str,
) -> None:
    async def erase(base_url: str) -> None:
        if client is None:
            raise HTTPException(
                status_code=503, detail="web_research_erasure_unavailable"
            )
        try:
            response = await client.delete(
                f"{base_url.rstrip('/')}/agents/web-research/activity/users/{quote(user_id, safe='')}",
                headers={"Authorization": authorization} if authorization else {},
                timeout=10,
            )
            # Older runtimes predate this capability and cannot have recorded it.
            if response.status_code == 404:
                return
            response.raise_for_status()
        except httpx.HTTPError:
            raise HTTPException(
                status_code=503, detail="web_research_erasure_unavailable"
            ) from None

    results = await asyncio.gather(
        *(
            erase(source.base_url)
            for source in config.platform.runtime_catalog_sources
            if source.enabled
        ),
        return_exceptions=True,
    )
    if any(isinstance(result, BaseException) for result in results):
        raise HTTPException(status_code=503, detail="web_research_erasure_unavailable")
