# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from typing import Annotated, Dict, List, Literal, Optional, Union

from fred_core import (
    LogStorageConfig,
    ModelConfiguration,
    OpenSearchStoreConfig,
    PostgresStoreConfig,
    SecurityConfiguration,
    StoreConfig,
)
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field, field_validator

from agentic_backend.core.agents.agent_spec import AgentTuning, MCPServerConfiguration

logger = logging.getLogger(__name__)  # Logger definition added


class StorageConfig(BaseModel):
    postgres: PostgresStoreConfig
    opensearch: OpenSearchStoreConfig
    agent_store: StoreConfig
    session_store: StoreConfig
    history_store: StoreConfig
    feedback_store: StoreConfig
    kpi_store: StoreConfig
    log_store: Optional[LogStorageConfig] = Field(
        default=None, description="Optional log store"
    )


class TimeoutSettings(BaseModel):
    connect: Optional[int] = Field(
        5, description="Time to wait for a connection in seconds."
    )
    read: Optional[int] = Field(
        15, description="Time to wait for a response in seconds."
    )


class RecursionConfig(BaseModel):
    recursion_limit: int


class AgentChatOptions(BaseModel):
    search_policy_selection: bool = False
    libraries_selection: bool = False
    record_audio_files: bool = True
    attach_files: bool = True


# ---------------- Base: shared identity + UX + tuning ----------------


class BaseAgent(BaseModel):
    """
    Fred rationale:
    - This base carries only identity, UX hints, and optional tuning hooks.
    - Behavior knobs live in `tuning_values` and are governed by `tuning_spec`.
    - Agents created from UI can omit `class_path`.
    """

    name: str
    enabled: bool = True
    class_path: Optional[str] = None  # None → dynamic/UI agent
    tuning: Optional[AgentTuning] = None
    chat_options: AgentChatOptions = AgentChatOptions()
    # Added for backward compatibility with older YAML files
    mcp_servers: List[MCPServerConfiguration] = Field(
        default_factory=list,
        deprecated=True,
        description="DEPRECATED: Use the global 'mcp' catalog and the 'mcp_servers' field in AgentTuning with references instead.",
    )

    @field_validator("mcp_servers", mode="after")
    @classmethod
    def warn_on_deprecated_mcp_servers(cls, v: List[MCPServerConfiguration], info):
        """Logs a warning if the deprecated agent-level mcp_servers field is used."""
        # Only log if the deprecated field was actually provided with content and we can infer the agent name
        if v and info.data.get("name"):
            logger.warning(
                "DEPRECATION WARNING for agent '%s': 'mcp_servers' is deprecated. "
                "Please migrate the full MCP server configuration to the global 'mcp' "
                "section in your configuration file and update the agent's tuning "
                "to use 'mcp_servers' (references).",
                info.data.get("name"),
            )
        return v


# ---------------- Agent: a regular single agent ----------------
class Agent(BaseAgent):
    """
    Why this subclass:
    - Regular agents don’t own crew. They can be *selected* into a leader’s crew.
    """

    type: Literal["agent"] = "agent"


# ---------------- Leader: declares its crew (and only here) ----------------
class Leader(BaseAgent):
    """
    Why this subclass:
    - Crew membership is defined *once*, at the leader level, to avoid drift.
    - You can include by names and/or by tags; optional excludes too.
    """

    type: Literal["leader"] = "leader"
    crew: List[str] = Field(
        default_factory=list,
        description="Names of agents in this leader's crew (if any).",
    )


# ---------------- Discriminated union for IO (YAML ⇄ DB ⇄ API) ----------------
AgentSettings = Annotated[Union[Agent, Leader], Field(discriminator="type")]


class AIConfig(BaseModel):
    knowledge_flow_url: str = Field(
        ...,
        description="URL of the Knowledge Flow backend.",
    )
    timeout: TimeoutSettings = Field(
        ..., description="Timeout settings for the AI client."
    )
    use_static_config_only: Optional[bool] = Field(
        True,
        description=(
            "If true, only static agent configurations from YAML are used; "
            "persistent configurations are ignored."
        ),
    )
    default_chat_model: ModelConfiguration = Field(
        ...,
        description="Default chat model configuration for all agents and services.",
    )
    default_language_model: Optional[ModelConfiguration] = Field(
        None,
        description="Default language model configuration for all agents and services (Optional).",
    )
    agents: List[AgentSettings] = Field(
        default_factory=list, description="List of AI agents."
    )


class FrontendFlags(BaseModel):
    enableK8Features: bool = False
    enableElecWarfare: bool = False


class Properties(BaseModel):
    logoName: str = "fred"
    siteDisplayName: str = "Fred"


class FrontendSettings(BaseModel):
    feature_flags: FrontendFlags
    properties: Properties


class AppConfig(BaseModel):
    name: Optional[str] = "Agentic Backend"
    base_url: str = "/agentic/v1"
    address: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    reload: bool = False
    reload_dir: str = "."


class McpConfiguration(BaseModel):
    servers: List[MCPServerConfiguration] = Field(
        default_factory=list,
        description="List of MCP servers defined for this environment.",
    )

    def get_server(self, name: str) -> Optional[MCPServerConfiguration]:
        """
        Retrieve an MCP server by logical name.
        Returns None if not found or disabled.
        """
        for s in self.servers:
            if s.name == name and s.enabled:
                return s
        return None

    def as_dict(self) -> Dict[str, MCPServerConfiguration]:
        """
        Fred rationale:
        - Useful for fast lookup and resolver integration.
        - Used by RuntimeContext → MCPRuntime to resolve URLs dynamically.
        """
        return {s.name: s for s in self.servers if s.enabled}


class Configuration(BaseModel):
    app: AppConfig
    security: SecurityConfiguration
    frontend_settings: FrontendSettings
    ai: AIConfig
    mcp: McpConfiguration = Field(
        default_factory=McpConfiguration,
        description="Microservice Communication Protocol (MCP) server configurations.",
    )
    storage: StorageConfig


class ChatContextMessage(SystemMessage):
    def __init__(self, content: str):
        super().__init__(content=content)
