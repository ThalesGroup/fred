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

from typing import Any, Dict, List, Optional, Literal, Union, Annotated
from datetime import datetime
from enum import Enum
import os
from pydantic import BaseModel, model_validator, Field
from fred_core import SecurityConfiguration, OpenSearchStorageConfig


# ----------------------------------------------------------------------
# Enums
# ----------------------------------------------------------------------


class HttpSchemeEnum(Enum):
    HTTP = "http"
    HTTPS = "https"


class DatabaseTypeEnum(str, Enum):
    csv = "csv"


class DAOTypeEnum(str, Enum):
    file = "file"


class PrecisionEnum(str, Enum):
    T = "T"
    H = "H"
    D = "D"
    W = "W"
    M = "M"
    Y = "Y"
    NONE = "NONE"

    def to_pandas_precision(self) -> str | None:
        match self:
            case self.T:
                return "min"
            case self.H:
                return "h"
            case self.W:
                return "W"
            case self.M:
                return "M"
            case self.Y:
                return "Y"
            case self.NONE:
                return None


class SampleDataType(str, Enum):
    AVERAGE = "average"
    SUM = "sum"


class CaseInsensitiveEnum(Enum):
    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            value_lower = value.lower()
            for member in cls:
                if member.value.lower() == value_lower:
                    return member
        return None


class WorkloadKind(CaseInsensitiveEnum):
    DEPLOYMENT = "Deployment"
    STATEFUL_SET = "StatefulSet"
    DAEMON_SET = "DaemonSet"
    JOB = "Job"
    CRONJOB = "CronJob"


# ----------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------


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


class PathOrIndexPrefix(BaseModel):
    energy_mix: str
    carbon_footprint: str
    energy_footprint: str
    financial_footprint: str
    frequencies: str
    sensors_test_new: str
    mission: str
    radio: str
    signal_identification_guide: str


class DatabaseConfiguration(BaseModel):
    type: DatabaseTypeEnum
    csv_files: Optional[PathOrIndexPrefix] = None
    host: Optional[str] = None
    port: Optional[int] = None
    scheme: Optional[HttpSchemeEnum] = HttpSchemeEnum.HTTP
    username: Optional[str] = None
    password: Optional[str] = None
    index_prefix: Optional[PathOrIndexPrefix] = None

    @model_validator(mode="after")
    def check_fields(self) -> "DatabaseConfiguration":
        match self.type:
            case DatabaseTypeEnum.csv:
                required_fields = ["csv_files"]
            case _:
                required_fields = []

        missing_fields = [
            field for field in required_fields if getattr(self, field) is None
        ]
        if missing_fields:
            raise ValueError(
                f"With type '{self.type}', the following fields are required: {', '.join(missing_fields)}"
            )
        return self


class KubernetesConfiguration(BaseModel):
    kube_config: str
    aws_config: Optional[str] = None
    timeout: TimeoutSettings


# ----------------------------------------------------------------------
# Services and Agents — now as lists!
# ----------------------------------------------------------------------


class RecursionConfig(BaseModel):
    recursion_limit: int


class ServicesSettings(BaseModel):
    name: str = Field(..., description="Service identifier name.")
    enabled: bool = Field(default=True, description="Whether the service is enabled.")
    settings: Dict[str, Any] = Field(
        default_factory=dict, description="Service-specific settings."
    )
    model: ModelConfiguration = Field(
        ...,
        description="AI model configuration for this service.",
    )


class AgentSettings(BaseModel):
    type: Literal["mcp", "custom", "leader"] = "custom"
    name: str
    class_path: Optional[str] = None
    enabled: bool = True
    categories: List[str] = Field(default_factory=list)
    settings: Dict[str, Any] = Field(default_factory=dict)
    model: ModelConfiguration
    tag: Optional[str] = None
    mcp_servers: Optional[List[MCPServerConfiguration]] = Field(default_factory=list)
    max_steps: Optional[int] = 10
    description: Optional[str] = None
    base_prompt: Optional[str] = None
    nickname: Optional[str] = None
    role: Optional[str] = None
    icon: Optional[str] = None


class AIConfig(BaseModel):
    timeout: TimeoutSettings = Field(
        ..., description="Timeout settings for the AI client."
    )
    default_model: ModelConfiguration = Field(
        ...,
        description="Default model configuration for all agents and services.",
    )
    services: List[ServicesSettings] = Field(
        default_factory=list, description="List of AI services."
    )
    agents: List[AgentSettings] = Field(
        default_factory=list, description="List of AI agents."
    )
    recursion: RecursionConfig = Field(
        ..., description="Number of max recursion while using the model"
    )

    @model_validator(mode="after")
    def validate_unique_names(self):
        service_names = [service.name for service in self.services]
        agent_names = [agent.name for agent in self.agents]
        duplicates = set(
            name
            for name in service_names + agent_names
            if (service_names + agent_names).count(name) > 1
        )
        if duplicates:
            raise ValueError(
                f"Duplicate service or agent names found: {', '.join(duplicates)}"
            )
        return self

    def apply_default_models(self):
        """
        Apply default model configuration to all agents and services if not specified.
        """

        def merge(target: ModelConfiguration) -> ModelConfiguration:
            defaults = self.default_model.model_dump(exclude_unset=True)
            target_dict = target.model_dump(exclude_unset=True)
            merged_dict = {**defaults, **target_dict}
            return ModelConfiguration(**merged_dict)

        for service in self.services:
            if service.enabled:
                service.model = merge(service.model)

        for agent in self.agents:
            if agent.enabled:
                agent.model = merge(agent.model)


# ----------------------------------------------------------------------
# Storage configurations
# ----------------------------------------------------------------------

## ----------------------------------------------------------------------
## Session storage configurations
## ----------------------------------------------------------------------


class InMemoryStorageConfig(BaseModel):
    type: Literal["in_memory"]


class OpenSessionSearchStorageConfig(BaseModel):
    type: Literal["opensearch"]
    host: str = Field(
        default="https://localhost:9200", description="URL of the Opensearch host"
    )
    username: Optional[str] = Field(
        default_factory=lambda: os.getenv("OPENSEARCH_USER"),
        description="Opensearch username",
    )
    password: Optional[str] = Field(
        default_factory=lambda: os.getenv("OPENSEARCH_PASSWORD"),
        description="Opensearch user password",
    )
    secure: bool = Field(default=False, description="Use TLS with Opensearch")
    verify_certs: bool = Field(default=False, description="Verify certificates")
    sessions_index: str = Field(
        default="active-sessions-index", description="Index where sessions are stored"
    )
    history_index: str = Field(
        default="chat-interactions-index",
        description="Index where messages histories are stored",
    )


SessionStorageConfig = Annotated[
    Union[InMemoryStorageConfig, OpenSessionSearchStorageConfig], Field(discriminator="type")
]

###########################################################
#
#  --- Dynamic Agents Storage Configuration
#


class DuckdbDynamicAgentStorage(BaseModel):
    type: Literal["duckdb"]
    duckdb_path: str = Field(
        default="~/.fred/agentic/db.duckdb",
        description="Path to the DuckDB database file.",
    )


DynamicAgentStorageConfig = Annotated[
    Union[DuckdbDynamicAgentStorage, OpenSearchStorageConfig], Field(discriminator="type")
]

###########################################################
#
#  --- Feedback Storage Configuration
#


class DuckdbFeedbackStorage(BaseModel):
    type: Literal["duckdb"]
    duckdb_path: str = Field(
        default="~/.fred/agentic/db.duckdb",
        description="Path to the DuckDB database file.",
    )


FeedbackStorageConfig = Annotated[Union[DuckdbFeedbackStorage, OpenSearchStorageConfig], Field(discriminator="type")]

# ----------------------------------------------------------------------
# Other configurations
# ----------------------------------------------------------------------


class DAOConfiguration(BaseModel):
    type: DAOTypeEnum
    base_path: Optional[str] = Field(default="/tmp")
    max_cached_delay_seconds: Optional[int] = Field(60)


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
    database: DatabaseConfiguration
    kubernetes: KubernetesConfiguration
    ai: AIConfig
    dao: DAOConfiguration
    feedback_storage: FeedbackStorageConfig = Field(
        ..., description="Feedback Storage configuration"
    )
    session_storage: SessionStorageConfig = Field(
        ..., description="Session Storage configuration"
    )
    agent_storage: DynamicAgentStorageConfig = Field(
        ..., description="Agents Storage configuration"
    )


class OfflineStatus(BaseModel):
    is_offline: bool


class Window(BaseModel):
    start: datetime
    end: datetime
    total: float


class Difference(BaseModel):
    value: float
    percentage: float


class CompareResult(BaseModel):
    cluster: str
    unit: str
    window_1: Window
    window_2: Window
    difference: Difference


class Series(BaseModel):
    timestamps: List[datetime]
    values: List[float]
    auc: float
    unit: str
