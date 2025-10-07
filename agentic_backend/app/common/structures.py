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

from app.core.agents.agent_spec import AgentTuning


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


class MCPServerConfiguration(BaseModel):
    name: str
    transport: Optional[str] = Field(
        "sse",
        description="MCP server transport. Can be sse, stdio, websocket or streamable_http",
    )
    url: Optional[str] = Field(None, description="URL and endpoint of the MCP server")
    sse_read_timeout: Optional[int] = Field(
        60 * 5,
        description="How long (in seconds) the client will wait for a new event before disconnecting",
    )
    command: Optional[str] = Field(
        None,
        description="Command to run for stdio transport. Can be uv, uvx, npx and so on.",
    )
    args: Optional[List[str]] = Field(
        None,
        description="Args to give the command as a list. ex:  ['--directory', '/directory/to/mcp', 'run', 'server.py']",
    )
    env: Optional[Dict[str, str]] = Field(
        None, description="Environment variables to give the MCP server"
    )


class RecursionConfig(BaseModel):
    recursion_limit: int


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
    model: Optional[ModelConfiguration] = None
    # User-facing discovery (what leaders & UI filter on)
    tags: List[str] = Field(default_factory=list)
    role: str
    description: str

    # Optional: spec declares allowed tunables; values store overrides
    tuning: Optional[AgentTuning] = None
    mcp_servers: List[MCPServerConfiguration] = Field(
        default_factory=list,
        description="List of active MCP server configurations for this agent.",
    )


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
        description="Default model configuration for all agents and services.",
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


class Configuration(BaseModel):
    app: AppConfig
    security: SecurityConfiguration
    frontend_settings: FrontendSettings
    ai: AIConfig
    storage: StorageConfig


class ChatContextMessage(SystemMessage):
    def __init__(self, content: str):
        super().__init__(content=content)
