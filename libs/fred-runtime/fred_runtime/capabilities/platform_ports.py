# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Turn-free platform ports for capability code: the model port injected on the
save path, and the team authorizer bound before every capability route.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence

from fastapi import Depends, HTTPException, Request, status
from fred_core.common.team_id import is_personal_team_ref, personal_team_id
from fred_core.security.models import AuthorizationError
from fred_core.security.oidc import get_current_user
from fred_core.security.rebac.rebac_engine import RebacEngine, TeamPermission
from fred_core.security.structure import KeycloakUser
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.models import AgentDefinition, ExecutionCategory
from fred_sdk.contracts.runtime import (
    CAPABILITY_TEAM_AUTHORIZER_STATE,
    CapabilityModelPort,
    CapabilityModelUnavailableError,
    CapabilityTeamAuthorizer,
)
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import BaseModel, ConfigDict, ValidationError

from ..model_routing.authz import usable_model_capability_ids
from ..model_routing.contracts import ModelNotUsableError, TeamRoutingProfileDriftError
from ..model_routing.provider import RoutedChatModelFactory
from ..runtime_context import get_runtime_context_or_none


class CapabilitySaveRouting(BaseModel):
    """Team routing snapshot control-plane sends as validate-config query
    parameters. Client-tier, as at prepare-execution: the port still applies
    the team's usable models, and no platform binding is accepted here."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    template_agent_id: str | None = None
    chat_default_profile_id: str | None = None
    agent_profile_overrides: dict[str, str] | None = None


def parse_save_routing(params: Mapping[str, str]) -> CapabilitySaveRouting | None:
    """Parse the routing query parameters; none means pod-local routing."""
    if not any(key in params for key in CapabilitySaveRouting.model_fields):
        return None
    try:
        raw_overrides = params.get("agent_profile_overrides")
        return CapabilitySaveRouting(
            template_agent_id=params.get("template_agent_id") or None,
            chat_default_profile_id=params.get("chat_default_profile_id") or None,
            agent_profile_overrides=(
                json.loads(raw_overrides) if raw_overrides else None
            ),
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid model routing parameters: {exc}",
        ) from exc


class _RoutingKeyDefinition(AgentDefinition):
    """Model routing reads `agent_id` only; this carries nothing else."""


class RoutedCapabilityModelPort(CapabilityModelPort):
    """`CapabilityModelPort` over the pod's routed chat-model factory."""

    def __init__(
        self,
        *,
        binding: BoundRuntimeContext,
        routing_agent_id: str,
        factory: object | None,
        rebac: RebacEngine | None,
    ) -> None:
        self._binding = binding
        self._definition = _RoutingKeyDefinition(
            agent_id=routing_agent_id,
            role="capability model",
            description="Turn-free capability model routing key.",
            execution_category=ExecutionCategory.REACT,
        )
        self._factory = factory
        self._rebac = rebac
        self._resolved: BoundRuntimeContext | None = None
        self._resolve_lock = asyncio.Lock()

    async def ainvoke(
        self,
        messages: Sequence[BaseMessage],
        *,
        profile_id: str | None = None,
        require_vision: bool = False,
    ) -> AIMessage:
        factory = self._factory
        if not isinstance(factory, RoutedChatModelFactory):
            raise CapabilityModelUnavailableError("No routed chat model on this pod.")
        binding = await self._usable_binding()
        try:
            model, selection = factory.build_for_chat(
                definition=self._definition, binding=binding, profile_id=profile_id
            )
        except (
            ModelNotUsableError,
            TeamRoutingProfileDriftError,
            KeyError,
            ValueError,
        ) as exc:
            raise CapabilityModelUnavailableError(str(exc)) from exc
        if require_vision and not factory.supports_vision(selection):
            raise CapabilityModelUnavailableError(
                f"Model profile {selection.profile_id!r} does not support vision."
            )
        result = await model.ainvoke(list(messages))
        if not isinstance(result, AIMessage):
            raise TypeError(f"Chat model returned {type(result).__name__}.")
        return result

    async def _usable_binding(self) -> BoundRuntimeContext:
        """The save binding plus the team's usable models, queried once."""
        if self._resolved is not None:
            return self._resolved
        async with self._resolve_lock:
            if self._resolved is None:
                team_id = self._binding.runtime_context.team_id
                ids = (
                    await usable_model_capability_ids(self._rebac, team_id)
                    if team_id
                    else None
                )
                self._resolved = self._binding.model_copy(
                    update={"usable_model_ids": tuple(ids) if ids is not None else None}
                )
            return self._resolved


async def require_team_permission(
    *,
    user: KeycloakUser | None,
    enforce: bool,
    rebac: RebacEngine | None,
    team_id: str,
    permission: TeamPermission,
    denied: str,
) -> None:
    """403 unless the caller holds `permission` on the team. A personal space is
    its owner's only; without ReBAC the check is identity-only; `enforce=False`
    (security disabled) allows everything."""
    if not enforce:
        return
    if user is None:
        raise _forbidden(denied)
    if is_personal_team_ref(team_id):
        if team_id != personal_team_id(user.uid):
            raise _forbidden(denied)
        return
    if rebac is None or not rebac.enabled:
        return
    try:
        await rebac.check_user_team_permission_or_raise(user, permission, team_id)
    except AuthorizationError as exc:
        raise _forbidden(denied) from exc


class RebacCapabilityTeamAuthorizer(CapabilityTeamAuthorizer):
    """Agent-editor check on a team, as control-plane applies it to agent edits."""

    def __init__(
        self, *, user: KeycloakUser | None, enforce: bool, rebac: RebacEngine | None
    ) -> None:
        self._user = user
        self._enforce = enforce
        self._rebac = rebac

    async def require_agent_editor(self, team_id: str) -> None:
        await require_team_permission(
            user=self._user,
            enforce=self._enforce,
            rebac=self._rebac,
            team_id=team_id,
            permission=TeamPermission.CAN_UPDATE_AGENTS,
            denied=AGENT_EDITOR_DENIED,
        )


AGENT_EDITOR_DENIED = "You cannot edit the agents of this team."


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def team_authorizer_binder(*, security_enabled: bool) -> Callable[..., Awaitable[None]]:
    """Router dependency binding the caller's `CapabilityTeamAuthorizer`
    on the request, read back by `fred_sdk`'s `capability_team_authorizer`."""

    if security_enabled:

        async def _bind_secured(
            request: Request, user: object = Depends(get_current_user)
        ) -> None:
            _bind(request, user if isinstance(user, KeycloakUser) else None, True)

        return _bind_secured

    async def _bind_open(request: Request) -> None:
        _bind(request, None, False)

    return _bind_open


def _bind(request: Request, user: KeycloakUser | None, enforce: bool) -> None:
    runtime = get_runtime_context_or_none()
    rebac = runtime.config.rebac_engine if runtime is not None else None
    authorizer = RebacCapabilityTeamAuthorizer(user=user, enforce=enforce, rebac=rebac)
    setattr(request.state, CAPABILITY_TEAM_AUTHORIZER_STATE, authorizer)
