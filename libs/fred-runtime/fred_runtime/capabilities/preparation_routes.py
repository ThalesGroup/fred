# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Read current preparation results for authenticated capability routes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException
from fred_core.filesystem.structures import BaseFilesystem
from fred_sdk.contracts.runtime import CapabilityPreparationReader


class RuntimePreparationRouteReader(CapabilityPreparationReader):
    def __init__(
        self,
        *,
        control_plane_url: str,
        client: httpx.AsyncClient,
        filesystem: BaseFilesystem,
        authorization: str | None,
    ) -> None:
        self._url = control_plane_url.rstrip("/")
        self._client = client
        self._filesystem = filesystem
        self._authorization = authorization
        self._allowed: set[str] = set()

    async def agent_status(
        self, team_id: str, agent_instance_id: str, capability_id: str
    ) -> Mapping[str, Any] | None:
        path = (
            f"/teams/{quote(team_id, safe='')}/agent-instances/"
            f"{quote(agent_instance_id, safe='')}/preparations"
        )
        headers = {"Authorization": self._authorization} if self._authorization else {}
        response = await self._client.get(
            self._url + path, params={"limit": 100}, headers=headers
        )
        if response.status_code == 404:
            return None
        if response.status_code in (401, 403):
            raise HTTPException(
                status_code=403, detail="Agent preparation access denied"
            )
        response.raise_for_status()
        for item in response.json().get("items", []):
            if item.get("capability_id") != capability_id:
                continue
            reference = item.get("result_reference")
            if isinstance(reference, str):
                self._check_reference(reference)
                self._allowed.add(reference)
            return item
        return None

    async def read_result(self, reference: str) -> bytes:
        if reference not in self._allowed:
            raise PermissionError("Preparation artifact was not authorized")
        return await self._read(reference)

    async def read_sibling(self, reference: str, filename: str) -> bytes:
        path = self._sibling_path(reference, filename)
        return await self._read(path)

    async def sibling_exists(self, reference: str, filename: str) -> bool:
        return await self._filesystem.exists(self._sibling_path(reference, filename))

    def _sibling_path(self, reference: str, filename: str) -> str:
        if reference not in self._allowed:
            raise PermissionError("Preparation artifact was not authorized")
        if (
            not filename
            or "/" in filename
            or "\\" in filename
            or filename in (".", "..")
        ):
            raise ValueError("Invalid preparation artifact filename")
        return reference.rpartition("/")[0] + "/" + filename

    async def _read(self, path: str) -> bytes:
        content = await self._filesystem.read(path)
        if len(content) > 64 * 1024 * 1024:
            raise ValueError("Preparation artifact exceeds route limit")
        return content

    @staticmethod
    def _check_reference(reference: str) -> None:
        parts = reference.split("/")
        if (
            len(parts) != 4
            or parts[0] != "capability-results"
            or any(not part or part in (".", "..") for part in parts)
        ):
            raise ValueError("Invalid preparation result reference")
