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
from pydantic import BaseModel, Field

from agentic_backend.core.agents.agent_spec import AgentTuning, MCPServerConfiguration


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
    default_chat_model: ModelConfiguration = Field(
        ...,
        description="Default chat model configuration for all agents and services.",
    )
    default_language_model: ModelConfiguration = Field(
        ...,
        description="Default language model configuration for all agents and services.",
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
    mcp: McpConfiguration
    storage: StorageConfig


class ChatContextMessage(SystemMessage):
    def __init__(self, content: str):
        super().__init__(content=content)
