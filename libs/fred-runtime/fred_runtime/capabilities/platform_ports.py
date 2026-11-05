# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Capability administration delegates rights to Weaver's Control Plane."""

from collections.abc import Awaitable, Callable, Sequence
from uuid import UUID

import httpx
from fastapi import HTTPException, Request
from fred_sdk.contracts.runtime import (
    CAPABILITY_PLATFORM_MODEL_STATE,
    CAPABILITY_TEAM_AUTHORIZER_STATE,
    CapabilityModelPort,
    CapabilityModelUnavailableError,
    CapabilityTeamAuthorizer,
)
from langchain_core.messages import AIMessage, BaseMessage

from fred_runtime.app.authorization import require_permission
from fred_runtime.common.outbound_credentials import static_person_provider
from fred_runtime.runtime_context import get_runtime_context


class WeaverCapabilityAuthorizer(CapabilityTeamAuthorizer):
    def __init__(self, authorization: str | None) -> None:
        self._authorization = authorization
        self.runtime_id = get_runtime_context().config.service_name

    async def require_agent_editor(self, team_id: str) -> None:
        # The SDK field is historical; Weaver sends a canonical space UUID.
        await require_permission(self._authorization, "write", space_id=team_id)

    async def require_preparation_access(
        self, reference: str, space_id: str, agent_instance_id: str | None
    ) -> None:
        await self.require_agent_editor(space_id)
        runtime = get_runtime_context().config
        if (
            not runtime.control_plane_url
            or runtime.control_plane_http_client is None
            or not self.runtime_id
        ):
            raise HTTPException(503, "authorization_unavailable")
        params = {"runtime_id": self.runtime_id}
        if agent_instance_id is not None:
            params["agent_instance_id"] = str(UUID(agent_instance_id))
        token = (self._authorization or "").partition(" ")[2].strip()
        credentials = await static_person_provider(token).credentials()
        try:
            # The CP resolves the current own or common template on this logical pod.
            response = await runtime.control_plane_http_client.get(
                f"{runtime.control_plane_url.rstrip('/')}/spaces/{UUID(space_id)}/powerpoint-template"
                + ("/settings" if agent_instance_id is None else ""),
                params=params,
                headers={"Authorization": credentials.authorization},
                auth=None,
                follow_redirects=False,
                timeout=10,
            )
            resolved = response.json() if response.status_code == 200 else {}
            if agent_instance_id is None:
                resolved = resolved.get("current", {})
            if resolved.get("analysis_reference") != reference:
                raise HTTPException(403, "preparation_access_denied")
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(503, "authorization_unavailable") from exc

    async def require_capability_manager(self) -> None:
        await require_permission(self._authorization, "manage_platform")


class UnavailableCapabilityModelPort(CapabilityModelPort):
    """Structural analysis remains available without turn-free model authority."""

    async def ainvoke(
        self,
        messages: Sequence[BaseMessage],
        *,
        profile_id: str | None = None,
        require_vision: bool = False,
    ) -> AIMessage:
        raise CapabilityModelUnavailableError(
            "Template vision labeling is not connected to Weaver inference admission."
        )


def team_authorizer_binder(*, security_enabled: bool) -> Callable[..., Awaitable[None]]:
    # CP authorization stays mandatory even when the pod's local JWT check is off.
    async def bind(request: Request) -> None:
        setattr(
            request.state,
            CAPABILITY_TEAM_AUTHORIZER_STATE,
            WeaverCapabilityAuthorizer(request.headers.get("Authorization")),
        )
        setattr(
            request.state,
            CAPABILITY_PLATFORM_MODEL_STATE,
            UnavailableCapabilityModelPort(),
        )

    return bind
