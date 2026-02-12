# Copyright Thales 2025
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

import asyncio
import logging
from enum import Enum
from typing import List, Optional, Tuple, Union
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver
from a2a.client.errors import A2AClientJSONError
from a2a.types import AgentCard
from a2a.utils.constants import EXTENDED_AGENT_CARD_PATH
from fred_core import (
    Action,
    AgentPermission,
    KeycloakUser,
    RebacDisabledResult,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    TeamPermission,
    authorize,
)

from agentic_backend.application_context import get_agent_store, get_rebac_engine
from agentic_backend.common.structures import (
    Agent,
    AgentChatOptions,
    AgentSettings,
)
from agentic_backend.core.agents.a2a_proxy_agent import A2AProxyAgent
from agentic_backend.core.agents.agent_manager import (
    AgentAlreadyExistsException,
    AgentManager,
)
from agentic_backend.core.agents.basic_react_agent import (
    BASIC_REACT_TUNING,
    BasicReActAgent,
)

logger = logging.getLogger(__name__)


class OwnerFilter(str, Enum):
    """Filter agents by ownership type.

    - PERSONAL: only agents where the user is directly the owner
    - TEAM: only agents owned by the specified team (team_id required)
    """

    PERSONAL = "personal"
    TEAM = "team"


class MissingTeamIdError(Exception):
    """Raised when owner_filter is 'team' but no team_id is provided."""

    pass


def _class_path(obj_or_type: Union[type, object]) -> str:
    """Return fully-qualified class path, e.g. 'agentic_backend.agents.basic_react_agent.BasicReActAgent'."""
    t: type = obj_or_type if isinstance(obj_or_type, type) else type(obj_or_type)
    return f"{t.__module__}.{t.__name__}"


class AgentService:
    def __init__(self, agent_manager: AgentManager):
        self.agent_store = get_agent_store()
        self.agent_manager = agent_manager
        self.rebac = get_rebac_engine()

    async def list_agents(
        self,
        user: KeycloakUser,
        owner_filter: Optional[OwnerFilter] = None,
        team_id: Optional[str] = None,
    ) -> List[AgentSettings]:
        agents = await self.agent_store.load_all()

        authorized_ids = await self._resolve_authorized_agent_ids(
            user, owner_filter, team_id
        )
        if authorized_ids is not None:
            agents = [a for a in agents if a.id in authorized_ids]

        return agents

    async def get_agent_by_id(
        self, user: KeycloakUser, agent_id: str
    ) -> AgentSettings | None:
        await self.rebac.check_user_permission_or_raise(
            user, AgentPermission.READ, agent_id
        )

        return await self.agent_manager.get_agent_settings(agent_id)

    async def create_agent(
        self,
        user: KeycloakUser,
        name: str,
        *,
        agent_type: str = "basic",
        team_id: Optional[str] = None,
        a2a_base_url: Optional[str] = None,
        a2a_token: Optional[str] = None,
    ):
        """
        Builds, registers, and stores the MCP agent, including updating app context and saving to DuckDB.
        """
        # If team_id is provided, check user has permission to manage team agents
        if team_id:
            await self.rebac.check_user_permission_or_raise(
                user, TeamPermission.CAN_UPDATE_AGENTS, team_id
            )

        agent_id = str(uuid4())

        if agent_type == "a2a_proxy":
            if not a2a_base_url:
                raise AgentAlreadyExistsException(
                    "A2A base URL is required for an A2A proxy agent."
                )
            tuning = A2AProxyAgent.tuning
            card_payload = await self._fetch_a2a_card(a2a_base_url, a2a_token)
            agent_settings = Agent(
                id=agent_id,
                name=name,
                class_path=_class_path(A2AProxyAgent),
                enabled=True,
                tuning=tuning,
                metadata={
                    "a2a_base_url": a2a_base_url,
                    "a2a_token": a2a_token,
                    "a2a_card": card_payload,
                },
            )
            await self.agent_manager.create_dynamic_agent(agent_settings, tuning)
        else:
            agent_settings = Agent(
                id=agent_id,
                name=name,
                class_path=_class_path(BasicReActAgent),
                enabled=False,  # Start disabled until fully initialized
                tuning=BASIC_REACT_TUNING,  # default tuning
                # Start with all chat options off by default; UI can toggle them later.
                chat_options=AgentChatOptions(),
                mcp_servers=[],  # Empty list by default; to be configured later
            )
            await self.agent_manager.create_dynamic_agent(
                agent_settings, BASIC_REACT_TUNING
            )

        # Create ReBAC ownership: team owns the agent, or user owns the agent (personal agent)
        if team_id:
            await self.rebac.add_relation(
                Relation(
                    subject=RebacReference(type=Resource.TEAM, id=team_id),
                    relation=RelationType.OWNER,
                    resource=RebacReference(type=Resource.AGENT, id=agent_id),
                )
            )
        else:
            await self.rebac.add_user_relation(
                user,
                RelationType.OWNER,
                resource_type=Resource.AGENT,
                resource_id=agent_id,
            )

    async def update_agent(self, user: KeycloakUser, agent_settings: AgentSettings):
        await self.rebac.check_user_permission_or_raise(
            user, AgentPermission.UPDATE, agent_settings.id
        )

        await self.agent_manager.update_agent(new_settings=agent_settings)

    async def delete_agent(self, user: KeycloakUser, agent_id: str):
        await self.rebac.check_user_permission_or_raise(
            user, AgentPermission.DELETE, agent_id
        )

        await self.agent_manager.delete_agent(agent_id)

    @authorize(action=Action.UPDATE, resource=Resource.AGENTS)
    async def restore_static_agents(
        self, user: KeycloakUser, force_overwrite: bool = True
    ) -> None:
        await self.agent_manager.restore_static_agents(force_overwrite=force_overwrite)

    async def _resolve_authorized_agent_ids(
        self,
        user: KeycloakUser,
        owner_filter: Optional[OwnerFilter],
        team_id: Optional[str],
    ) -> set[str] | None:
        """Return the set of agent IDs the user is allowed to see, or None if ReBAC is disabled.

        When an owner_filter is provided, the result is intersected with the
        owner-filtered agent IDs so only readable agents matching the filter are returned.
        """
        readable_coro = self.rebac.lookup_user_resources(user, AgentPermission.READ)

        if owner_filter is None:
            readable_refs = await readable_coro
            if isinstance(readable_refs, RebacDisabledResult):
                return None
            return {ref.id for ref in readable_refs}

        # Determine the subject reference based on the filter
        if owner_filter == OwnerFilter.TEAM:
            if not team_id:
                raise MissingTeamIdError(
                    "team_id is required when owner_filter is 'team'"
                )
            subject_ref = RebacReference(type=Resource.TEAM, id=team_id)
        else:
            subject_ref = RebacReference(type=Resource.USER, id=user.uid)

        # Run lookups in parallel: security baseline + owner-filtered lookup
        readable_refs, owned = await asyncio.gather(
            readable_coro,
            self.rebac.lookup_resources(
                subject_ref, AgentPermission.OWNER, Resource.AGENT
            ),
        )
        if isinstance(readable_refs, RebacDisabledResult) or isinstance(
            owned, RebacDisabledResult
        ):
            return None

        readable_ids = {ref.id for ref in readable_refs}
        filtered_ids = {ref.id for ref in owned}
        return readable_ids & filtered_ids

    async def _fetch_a2a_card(
        self, base_url: str, token: Optional[str]
    ) -> Optional[dict]:
        """
        Resolve and return the agent card as a plain dict for persistence.
        Best-effort: if fetching or validation fails, returns None.
        """
        base, card_path = self._split_discovery_url(base_url)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resolver = A2ACardResolver(httpx_client=client, base_url=base)
                try:
                    card = await resolver.get_agent_card(relative_card_path=card_path)
                except A2AClientJSONError:
                    # Fallback for agents advertising protocolVersion instead of version
                    resp = await client.get(f"{base}/{card_path}")
                    resp.raise_for_status()
                    data = resp.json()
                    if "version" not in data and data.get("protocolVersion"):
                        data["version"] = data["protocolVersion"]
                    card = AgentCard.model_validate(data)

                if card.supports_authenticated_extended_card and token:
                    try:
                        card = await resolver.get_agent_card(
                            relative_card_path=EXTENDED_AGENT_CARD_PATH,
                            http_kwargs={
                                "headers": {"Authorization": f"Bearer {token}"}
                            },
                        )
                    except Exception:
                        logger.exception(
                            "[AGENT][A2A] Failed to fetch extended agent card; keeping public card."
                        )
                return card.model_dump(exclude_none=True)
        except Exception:
            logger.exception("[AGENT][A2A] Failed to fetch agent card during creation.")
            return None

    @staticmethod
    def _split_discovery_url(url: str) -> Tuple[str, str]:
        """
        Accept either a base URL (http://host:port) or a full discovery URL ending in /.well-known/agent-card.json.
        Returns (base_url_without_trailing_slash, relative_card_path).
        """
        cleaned = url.strip()
        default_path = ".well-known/agent-card.json"
        marker = "/.well-known/agent-card.json"
        if marker in cleaned:
            idx = cleaned.find(marker)
            base = cleaned[:idx] or cleaned
            path = cleaned[idx + 1 :]  # drop leading slash
            return base.rstrip("/"), path
        return cleaned.rstrip("/"), default_path
