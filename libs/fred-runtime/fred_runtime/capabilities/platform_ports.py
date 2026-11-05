# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Capability administration delegates rights to Weaver's Control Plane."""

from collections.abc import Awaitable, Callable, Sequence

from fastapi import Request
from fred_sdk.contracts.runtime import (
    CAPABILITY_PLATFORM_MODEL_STATE,
    CAPABILITY_TEAM_AUTHORIZER_STATE,
    CapabilityModelPort,
    CapabilityModelUnavailableError,
    CapabilityTeamAuthorizer,
)
from langchain_core.messages import AIMessage, BaseMessage

from fred_runtime.app.authorization import require_permission


class WeaverCapabilityAuthorizer(CapabilityTeamAuthorizer):
    def __init__(self, authorization: str | None) -> None:
        self._authorization = authorization

    async def require_agent_editor(self, team_id: str) -> None:
        # The SDK field is historical; Weaver sends a canonical space UUID.
        await require_permission(self._authorization, "write", space_id=team_id)

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
