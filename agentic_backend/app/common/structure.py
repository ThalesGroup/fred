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

#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

"""
Pydantic structure definitions to use in the carbon microservice
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, model_validator, Field, field_validator


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
    connect: Optional[int] = Field(5, description="Time to wait for a connection in seconds.")
    read: Optional[int] = Field(15, description="Time to wait for a response in seconds.")


class ModelConfiguration(BaseModel):
    provider: Optional[str] = Field(None, description="Provider of the AI model, e.g., openai, ollama, azure.")
    name: Optional[str] = Field(None, description="Model name, e.g., gpt-4o, llama2.")
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional provider-specific settings, e.g., Azure deployment name.")

class MCPServerConfiguration(BaseModel):
    name: str = Field(None, description="Name of the MCP server")
    transport: Optional[str] = Field("sse", description="MCP server transport. Can be sse, stdio, websocket or streamable_http")
    url: Optional[str] = Field(None, description="URL and endpoint of the MCP server")
    sse_read_timeout:  Optional[int] = Field(60 * 5, description="How long (in seconds) the client will wait for a new event before disconnecting")
    command: Optional[str] = Field(None, description="Command to run for stdio transport. Can be uv, uvx, npx and so on.")
    args: Optional[List[str]] = Field(None, description="Args to give the command as a list. ex:  ['--directory', '/directory/to/mcp', 'run', 'server.py']")
    env: Optional[Dict[str, str]] = Field(None, description="Environment variables to give the MCP server")
    
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

    @model_validator(mode='after')
    def check_fields(self) -> "DatabaseConfiguration":
        match self.type:
            case DatabaseTypeEnum.csv:
                required_fields = ['csv_files']
            case _:
                required_fields = []

        missing_fields = [field for field in required_fields if getattr(self, field) is None]
        if missing_fields:
            raise ValueError(f"With type '{self.type}', the following fields are required: {', '.join(missing_fields)}")
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
    settings: Dict[str, Any] = Field(default_factory=dict, description="Service-specific settings.")
    model: ModelConfiguration = Field(default_factory=ModelConfiguration, description="AI model configuration for this service.")


class AgentSettings(BaseModel):
    name: str = Field(..., description="Agent identifier name.")
    class_path: Optional[str] = Field(None, description="Path to the agent class.")
    enabled: bool = Field(default=True, description="Whether the agent is enabled.")
    categories: List[str] = Field(default_factory=list, description="List of categories for the agent.")
    settings: Dict[str, Any] = Field(default_factory=dict, description="Agent-specific settings (e.g., document directory, chunk size).")
    model: ModelConfiguration = Field(default_factory=ModelConfiguration, description="AI model configuration for this agent.")
    tag: Optional[str] = Field(None, description="Tag of the agent")
    mcp_servers: List[MCPServerConfiguration] = Field(default_factory=list, description="List of MCP servers associated to an agent.")
    max_steps: int = Field(None,description="Max step")


class AIConfig(BaseModel):
    timeout: TimeoutSettings = Field(None, description="Timeout settings for the AI client.")
    default_model: ModelConfiguration = Field(default_factory=ModelConfiguration, description="Default model configuration for all agents and services.")
    leader: AgentSettings = Field(default_factory=AgentSettings, description="Settings for the leader agent.")
    services: List[ServicesSettings] = Field(default_factory=list, description="List of AI services.")
    agents: List[AgentSettings] = Field(default_factory=list, description="List of AI agents.")
    recursion: RecursionConfig = Field(default_factory=int, description="Number of max recursion while using the model")


    @model_validator(mode='after')
    def validate_unique_names(self):
        service_names = [service.name for service in self.services]
        agent_names = [agent.name for agent in self.agents]
        duplicates = set(name for name in service_names + agent_names if (service_names + agent_names).count(name) > 1)
        if duplicates:
            raise ValueError(f"Duplicate service or agent names found: {', '.join(duplicates)}")
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

        if self.leader.enabled:
            self.leader.model = merge(self.leader.model)

        for service in self.services:
            if service.enabled:
                service.model = merge(service.model)

        for agent in self.agents:
            if agent.enabled:
                agent.model = merge(agent.model)


# ----------------------------------------------------------------------
# Other configurations
# ----------------------------------------------------------------------

class DAOConfiguration(BaseModel):
    type: DAOTypeEnum
    base_path: Optional[str] = Field(default="/tmp")
    max_cached_delay_seconds: Optional[int] = Field(60)


class Security(BaseModel):
    enabled: bool = True
    keycloak_url: str = "http://localhost:9080/realms/fred"
    client_id: str = "fred"
    authorized_origins: List[str] = ["http://localhost:5173"]


class FrontendFlags(BaseModel):
    enableK8Features: bool = False
    enableElecWarfare: bool = False

class Properties(BaseModel):
    logoName: str = 'fred'

class FrontendSettings(BaseModel):
    feature_flags: FrontendFlags
    properties: Properties

class MetricsStorageSettings(BaseModel):
    local_path: str = Field(..., description="The path of the local metrics store")

class FeedbackStorageSettings(BaseModel):
    local_path: str = Field(..., description="The path of the local metrics store")

class FeedbackStorageConfig(BaseModel):
    type: str = Field(..., description="The storage backend to use (e.g., 'local', 'opensearch')")
    settings: FeedbackStorageSettings

class MetricsStorageConfig(BaseModel):
    type: str = Field(..., description="The metrics store to use (e.g., 'local')")
    settings: MetricsStorageSettings

class Configuration(BaseModel):
    frontend_settings: FrontendSettings
    database: DatabaseConfiguration
    kubernetes: KubernetesConfiguration
    ai: AIConfig
    dao: DAOConfiguration
    security: Security
    feedback_storage: FeedbackStorageConfig = Field(..., description="Feedback Storage configuration")
    node_metrics_storage:  MetricsStorageConfig = Field(..., description="Node Monitoring Storage configuration")
    tool_metrics_storage:  MetricsStorageConfig = Field(..., description="Tool Monitoring Storage configuration")

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
