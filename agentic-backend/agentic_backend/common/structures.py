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
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from fred_core import (
    LogStorageConfig,
    ModelConfiguration,
    OpenSearchStoreConfig,
    PostgresStoreConfig,
    SecurityConfiguration,
    StoreConfig,
    TemporalSchedulerConfig,
)
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field, field_validator

from agentic_backend.core.agents.agent_spec import AgentTuning, MCPServerConfiguration

logger = logging.getLogger(__name__)  # Logger definition added


class StorageConfig(BaseModel):
    postgres: PostgresStoreConfig
    opensearch: Optional[OpenSearchStoreConfig] = Field(
        default=None, description="Optional OpenSearch store"
    )
    agent_store: StoreConfig
    task_store: Optional[StoreConfig] = Field(
        default=None,
        description="Task store backend (optional; workers may fall back to in-memory)",
    )
    mcp_servers_store: Optional[StoreConfig] = Field(
        default=None,
        description="Optional override for MCP servers store (defaults to agent_store backend).",
    )
    session_store: StoreConfig
    attachments_store: Optional[StoreConfig] = Field(
        default=None,
        description="Optional override for session attachments persistence (defaults to session_store backend).",
    )
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
    """
    UI toggles for the chat input.

    Fred rationale:
    - These flags control which optional pickers/actions appear next to the user message box.
    - They do not change agent behavior by themselves; they expose inputs the agent may consume.
    - All options are opt-in and default to False.
    """

    search_policy_selection: bool = Field(
        default=False,
        description=(
            "Show a selector to choose the retrieval/search policy (e.g., hybrid, semantic, strict) "
            "before sending a message."
        ),
    )
    libraries_selection: bool = Field(
        default=False,
        description=(
            "Display a picker to include document libraries/knowledge sources that the agent can use "
            "for this message (session-scoped context)."
        ),
    )
    include_corpus_in_search: bool = Field(
        default=True,
        description=(
            "Allow vector search on corpus documents. If false, corpus retrieval is disabled "
            "for this agent even when the client requests it."
        ),
    )
    record_audio_files: bool = Field(
        default=False,
        description=(
            "Add a microphone control to record a short audio clip and attach it to the message."
        ),
    )
    attach_files: bool = Field(
        default=False,
        description=(
            "Allow attaching local files (e.g., PDFs, images, text) to the message and show existing attachments."
        ),
    )
    search_rag_scoping: bool = Field(
        default=False,
        description=(
            "Expose a selector to decide how the agent should use the corpus: documents only, hybrid, or general knowledge only."
        ),
    )
    deep_search_delegate: bool = Field(
        default=False,
        description=(
            "Expose a toggle to delegate RAG retrieval to a senior agent (deep search) when available."
        ),
    )
    documents_selection: bool = Field(
        default=False,
        description=(
            "Display a picker to restrict retrieval to specific documents for this message."
        ),
    )


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
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional arbitrary metadata for integrations (e.g., A2A proxy config).",
    )
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
        ...,
        description="Timeout settings for the REST AI clients. This does not affect model calls.",
    )
    use_static_config_only: Optional[bool] = Field(
        True,
        description=(
            "If true, only static agent configurations from YAML are used; "
            "persistent configurations are ignored."
        ),
    )
    restore_max_exchanges: int = Field(
        20,
        description="Number of past exchanges to restore when initializing an agent session.",
    )

    max_concurrent_agents: int = Field(
        1024,
        description="Maximum number of agents that can be cached in memory for faster access.",
    )
    max_concurrent_sessions_per_user: int = Field(
        10,
        description=(
            "Maximum number of concurrent sessions allowed per user. This is used to prevent abuse and manage resource usage."
        ),
    )
    max_attached_files_per_user: int = Field(
        20,
        description="Maximum number of files a user can attach across all sessions.",
    )
    max_attached_file_size_mb: int = Field(
        50,
        description="Maximum size (in MB) for each attached file.",
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
    logoNameDark: str = "fred-dark"
    logoHeight: str = "36px"
    logoWidth: str = "36px"
    faviconName: str | None = None
    faviconNameDark: str | None = None
    siteDisplayName: str = "Fred"
    releaseBrand: Optional[str] = Field(
        default="fred",
        description="Optional brand slug used to resolve brand-specific assets (e.g., release notes). Defaults to 'fred'.",
    )
    agentsNicknameSingular: str = "agent"
    agentsNicknamePlural: str = "agents"
    agentIconPath: str | None = None
    contactSupportLink: str | None = None


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
    metrics_enabled: bool = True
    metrics_address: str = "127.0.0.1"
    metrics_port: int = 9000
    kpi_process_metrics_interval_sec: int = Field(
        0,
        description="Interval in seconds for processing and logging KPI metrics.",
    )
    kpi_log_summary_interval_sec: float = Field(
        default=0.0,
        description="Emit KPI summary logs every N seconds (bench/debug). Set 0 to disable.",
    )
    kpi_log_summary_top_n: int = Field(
        default=0,
        description="Top-N metrics to show in KPI summary logs. 0 means all / disabled.",
    )


class SchedulerConfig(BaseModel):
    enabled: bool = False
    backend: str = "temporal"
    temporal: TemporalSchedulerConfig = Field(default_factory=TemporalSchedulerConfig)


class McpConfiguration(BaseModel):
    servers: List[MCPServerConfiguration] = Field(
        default_factory=list,
        description="List of MCP servers defined for this environment.",
    )

    def get_server(self, id: str) -> Optional[MCPServerConfiguration]:
        """
        Retrieve an MCP server by logical name.
        Returns None if not found or disabled.
        """
        for s in self.servers:
            if s.id == id and s.enabled:
                return s
        return None

    def as_dict(self) -> Dict[str, MCPServerConfiguration]:
        """
        Fred rationale:
        - Useful for fast lookup and resolver integration.
        - Used by RuntimeContext → MCPRuntime to resolve URLs dynamically.
        """
        return {s.id: s for s in self.servers if s.enabled}


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
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)


class ChatContextMessage(SystemMessage):
    def __init__(self, content: str):
        super().__init__(content=content)
