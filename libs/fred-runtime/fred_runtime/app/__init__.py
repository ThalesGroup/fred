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
Agent app factory — reusable FastAPI wiring for agent pods.

Import from here:
    from fred_runtime.app import create_agent_app, AgentPodConfig, load_agent_pod_config
"""

from .agent_app import create_agent_app
from .config import (
    AgentPodConfig,
    LangfuseObservabilityConfig,
    PodAIConfig,
    PodAppConfig,
    PodObservabilityConfig,
    PodPlatformConfig,
    PodSchedulerConfig,
    PodStorageConfig,
    TracerBackend,
)
from .config_loader import (
    get_loaded_config_file_path,
    get_loaded_env_file_path,
    load_agent_pod_config,
)

__all__ = [
    "AgentPodConfig",
    "LangfuseObservabilityConfig",
    "PodAIConfig",
    "PodAppConfig",
    "PodObservabilityConfig",
    "PodPlatformConfig",
    "PodSchedulerConfig",
    "PodStorageConfig",
    "TracerBackend",
    "create_agent_app",
    "get_loaded_config_file_path",
    "get_loaded_env_file_path",
    "load_agent_pod_config",
]
