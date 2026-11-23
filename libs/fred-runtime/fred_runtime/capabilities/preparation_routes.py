# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Read current preparation results for authenticated capability routes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException
from fred_core.filesystem.structures import BaseFilesystem
from fred_sdk.contracts.runtime import (
    CapabilityPreparationManager,
    CapabilityPreparationReader,
)

from fred_runtime.common.outbound_credentials import OutboundCredentialProvider


class RuntimePreparationRouteReader(
    CapabilityPreparationReader, CapabilityPreparationManager
):
    def __init__(
        self,
        *,
        control_plane_url: str,
        runtime_id: str,
        client: httpx.AsyncClient,
        filesystem: BaseFilesystem,
        credentials: OutboundCredentialProvider,
        enabled_capabilities: tuple[str, ...] = (),
    ) -> None:
        self._url = control_plane_url.rstrip("/")
        self._runtime_id = runtime_id
        self._client = client
        self._filesystem = filesystem
        self._credentials = credentials
        self._enabled_capabilities = frozenset(enabled_capabilities)
        self._allowed: set[str] = set()

    def enabled(self, capability_id: str) -> bool:
        return capability_id in self._enabled_capabilities

    async def agent_status(
        self, team_id: str, agent_instance_id: str, capability_id: str
    ) -> Mapping[str, Any] | None:
        path = (
            f"/teams/{quote(team_id, safe='')}/agent-instances/"
            f"{quote(agent_instance_id, safe='')}/preparations"
        )
        authorization = (await self._credentials.credentials()).authorization
        headers = {"Authorization": authorization} if authorization else {}
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

    def _platform_path(self, capability_id: str, slot_key: str) -> str:
        return (
            "/platform/capability-preparations/"
            f"{quote(self._runtime_id, safe='')}/"
            f"{quote(capability_id, safe='')}/{quote(slot_key, safe='')}"
        )

    async def _platform_request(
        self, method: str, path: str, **kwargs: Any
    ) -> Mapping[str, Any]:
        authorization = (await self._credentials.credentials()).authorization
        headers = {"Authorization": authorization} if authorization else {}
        response = await self._client.request(
            method, self._url + path, headers=headers, **kwargs
        )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=response.status_code,
                detail="Platform preparation request failed",
            )
        return response.json()

    async def platform_status(
        self, capability_id: str, slot_key: str
    ) -> Mapping[str, Any]:
        result = await self._platform_request(
            "GET", self._platform_path(capability_id, slot_key)
        )
        for item in (result.get("active"), result.get("candidate")):
            if isinstance(item, dict) and isinstance(item.get("result_reference"), str):
                reference = item["result_reference"]
                self._check_reference(reference)
                self._allowed.add(reference)
        return result

    async def upload_platform_candidate(
        self,
        capability_id: str,
        slot_key: str,
        content: bytes,
        filename: str,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return await self._platform_request(
            "PUT",
            self._platform_path(capability_id, slot_key) + "/candidate",
            files={"file": (filename, content)},
            data={"config_json": json.dumps(dict(config))},
        )

    async def retry_platform_candidate(
        self, capability_id: str, slot_key: str
    ) -> Mapping[str, Any]:
        return await self._platform_request(
            "POST", self._platform_path(capability_id, slot_key) + "/candidate/retry"
        )

    async def refresh_platform_candidate(
        self, capability_id: str, slot_key: str, config: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return await self._platform_request(
            "POST",
            self._platform_path(capability_id, slot_key) + "/candidate/refresh",
            json=dict(config),
        )

    async def reset_platform_selection(
        self, capability_id: str, slot_key: str
    ) -> Mapping[str, Any]:
        return await self._platform_request(
            "DELETE", self._platform_path(capability_id, slot_key)
        )

    async def set_platform_settings(
        self, capability_id: str, slot_key: str, settings: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return await self._platform_request(
            "PUT",
            self._platform_path(capability_id, slot_key) + "/settings",
            json=dict(settings),
        )

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
