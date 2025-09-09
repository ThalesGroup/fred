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

from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field
from fred_core import (
    SecurityConfiguration,
    PostgresStoreConfig,
    OpenSearchStoreConfig,
    StoreConfig,
)


class StorageConfig(BaseModel):
    postgres: PostgresStoreConfig
    opensearch: OpenSearchStoreConfig
    agent_store: StoreConfig
    session_store: StoreConfig
    history_store: StoreConfig
    feedback_store: StoreConfig
    kpi_store: StoreConfig


class TimeoutSettings(BaseModel):
    connect: Optional[int] = Field(
        5, description="Time to wait for a connection in seconds."
    )
    read: Optional[int] = Field(
        15, description="Time to wait for a response in seconds."
    )


class ModelConfiguration(BaseModel):
    provider: Optional[str] = Field(
        None, description="Provider of the AI model, e.g., openai, ollama, azure."
    )
    name: Optional[str] = Field(None, description="Model name, e.g., gpt-4o, llama2.")
    settings: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional provider-specific settings, e.g., Azure deployment name.",
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


class AgentSettings(BaseModel):
    name: str  # a unique name
    class_path: str
    type: Literal["mcp", "custom", "leader"] = "custom"
    enabled: bool = True
    categories: List[str] = Field(default_factory=list)
    settings: Dict[str, Any] = Field(default_factory=dict)
    model: Optional[ModelConfiguration] = None
    tag: Optional[str] = None
    mcp_servers: Optional[List[MCPServerConfiguration]] = Field(default_factory=list)
    max_steps: Optional[int] = 10
    description: Optional[str] = None
    base_prompt: Optional[str] = None
    nickname: Optional[str] = None  # only used for UIs defaulting to name
    role: Optional[str] = None
    icon: Optional[str] = None


class AIConfig(BaseModel):
    knowledge_flow_url: str = Field(
        ...,
        description="URL of the Knowledge Flow backend.",
    )
    timeout: TimeoutSettings = Field(
        ..., description="Timeout settings for the AI client."
    )
    default_model: ModelConfiguration = Field(
        ...,
        description="Default model configuration for all agents and services.",
    )
    agents: List[AgentSettings] = Field(
        default_factory=list, description="List of AI agents."
    )
    recursion: RecursionConfig = Field(
        ..., description="Number of max recursion while using the model"
    )


class FrontendFlags(BaseModel):
    enableK8Features: bool = False
    enableElecWarfare: bool = False


class Properties(BaseModel):
    logoName: str = "fred"


class FrontendSettings(BaseModel):
    feature_flags: FrontendFlags
    properties: Properties
    security: SecurityConfiguration


class AppConfig(BaseModel):
    name: Optional[str] = "Agentic Backend"
    base_url: str = "/agentic/v1"
    address: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    reload: bool = False
    reload_dir: str = "."
    security: SecurityConfiguration


class Configuration(BaseModel):
    app: AppConfig
    frontend_settings: FrontendSettings
    ai: AIConfig
    storage: StorageConfig
