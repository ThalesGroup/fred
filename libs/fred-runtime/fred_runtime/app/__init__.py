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

from typing import TYPE_CHECKING

from .config import (
    AgentPodConfig,
    ConversationFilesystemQuotaConfig,
    GcsRuntimeFilesystemConfig,
    LangfuseObservabilityConfig,
    LocalRuntimeFilesystemConfig,
    MinioRuntimeFilesystemConfig,
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
from .filesystem_factory import build_runtime_filesystem

if TYPE_CHECKING:
    from .agent_app import create_agent_app


def __getattr__(name: str):
    if name == "create_agent_app":
        # Executors import app diagnostics without needing the FastAPI assembly.
        from .agent_app import create_agent_app

        globals()[name] = create_agent_app
        return create_agent_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AgentPodConfig",
    "ConversationFilesystemQuotaConfig",
    "GcsRuntimeFilesystemConfig",
    "LangfuseObservabilityConfig",
    "LocalRuntimeFilesystemConfig",
    "MinioRuntimeFilesystemConfig",
    "PodAIConfig",
    "PodAppConfig",
    "PodObservabilityConfig",
    "PodPlatformConfig",
    "PodSchedulerConfig",
    "PodStorageConfig",
    "TracerBackend",
    "build_runtime_filesystem",
    "create_agent_app",
    "get_loaded_config_file_path",
    "get_loaded_env_file_path",
    "load_agent_pod_config",
]
