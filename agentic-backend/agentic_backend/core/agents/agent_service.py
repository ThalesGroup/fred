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

import logging
from typing import Optional, Tuple, Union

import httpx
from a2a.client import A2ACardResolver
from a2a.client.errors import A2AClientJSONError
from a2a.types import AgentCard
from a2a.utils.constants import EXTENDED_AGENT_CARD_PATH
from fred_core import Action, KeycloakUser, Resource, authorize

from agentic_backend.application_context import get_agent_store
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


def _class_path(obj_or_type: Union[type, object]) -> str:
    """Return fully-qualified class path, e.g. 'agentic_backend.agents.basic_react_agent.BasicReActAgent'."""
    t: type = obj_or_type if isinstance(obj_or_type, type) else type(obj_or_type)
    return f"{t.__module__}.{t.__name__}"


class AgentService:
    def __init__(self, agent_manager: AgentManager):
        self.store = get_agent_store()
        self.agent_manager = agent_manager

    @authorize(action=Action.CREATE, resource=Resource.AGENTS)
    async def create_agent(
        self,
        user: KeycloakUser,
        name: str,
        *,
        agent_type: str = "basic",
        a2a_base_url: Optional[str] = None,
        a2a_token: Optional[str] = None,
    ):
        """
        Builds, registers, and stores the MCP agent, including updating app context and saving to DuckDB.
        """
        # Guard: disallow duplicates at the store level (with helpful diagnostics)
        existing = await self._safe_get(name)
        if existing:
            if not getattr(existing, "class_path", None):
                logger.warning(
                    "Agent name conflict with missing class_path: name='%s'. "
                    "Deleting stale entry then recreating.",
                    name,
                )
                try:
                    await self.store.delete(name)
                except Exception:
                    logger.exception(
                        "Failed to delete stale agent '%s' lacking class_path", name
                    )
                    raise AgentAlreadyExistsException(
                        f"Agent '{name}' already exists with invalid state (missing class_path). "
                        "Delete it manually and retry."
                    )
            else:
                logger.warning(
                    "Agent creation blocked: name='%s' already present in store "
                    "(class_path=%s, enabled=%s). If it does not appear in UI, delete it explicitly.",
                    name,
                    getattr(existing, "class_path", None),
                    getattr(existing, "enabled", None),
                )
                raise AgentAlreadyExistsException(
                    f"Agent '{name}' already exists in the persistent store. If it is hidden in UI, delete it then recreate."
                )

        if agent_type == "a2a_proxy":
            if not a2a_base_url:
                raise AgentAlreadyExistsException(
                    "A2A base URL is required for an A2A proxy agent."
                )
            tuning = A2AProxyAgent.tuning
            card_payload = await self._fetch_a2a_card(a2a_base_url, a2a_token)
            agent_settings = Agent(
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

    @authorize(action=Action.UPDATE, resource=Resource.AGENTS)
    async def update_agent(
        self, user: KeycloakUser, agent_settings: AgentSettings, is_global: bool
    ):
        # Delete existing agent (if any)
        # await self.agent_manager.unregister_agent(agent_settings)
        # self.store.delete(agent_settings.name)

        # Recreate it using the same logic as in create
        # return await self.build_and_register_mcp_agent(user, agent_settings)
        await self.agent_manager.update_agent(
            new_settings=agent_settings, is_global=is_global
        )
        self.agent_manager.log_current_settings()

    @authorize(action=Action.DELETE, resource=Resource.AGENTS)
    async def delete_agent(self, user: KeycloakUser, agent_name: str):
        # Unregister from memory
        await self.agent_manager.delete_agent(agent_name)

        # Delete from DuckDB
        await self.store.delete(agent_name)

        return {"message": f"✅ Agent '{agent_name}' deleted successfully."}

    @authorize(action=Action.UPDATE, resource=Resource.AGENTS)
    async def restore_static_agents(
        self, user: KeycloakUser, force_overwrite: bool = True
    ) -> None:
        await self.agent_manager.restore_static_agents(force_overwrite=force_overwrite)

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

    async def _safe_get(self, name: str) -> Optional[AgentSettings]:
        """Wrapper to protect create/update flows from store.get anomalies."""
        try:
            return await self.store.get(name)
        except Exception:
            logger.warning(
                "store.get raised unexpectedly while checking existence for agent=%s",
                name,
                exc_info=True,
            )
            return None
