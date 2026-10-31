# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Strict responses from the sole authorization authority."""

from typing import Any

import httpx
from fastapi import HTTPException


async def authorization_request(
    client: httpx.AsyncClient, url: str, body: dict[str, Any], **kwargs: Any
) -> dict[str, Any]:
    try:
        response = await client.post(url, json=body, follow_redirects=False, **kwargs)
        if response.status_code in (401, 403, 404, 409):
            raise HTTPException(response.status_code, "authorization_refused")
        if response.status_code != 200:
            raise HTTPException(503, "authorization_unavailable")
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Invalid authorization response")
        return result
    except (httpx.HTTPError, ValueError, RuntimeError):
        raise HTTPException(503, "authorization_unavailable") from None


def allowed_response(result: dict[str, Any]) -> bool:
    allowed = result.get("allowed")
    if type(allowed) is not bool:
        raise HTTPException(503, "authorization_unavailable")
    return allowed
