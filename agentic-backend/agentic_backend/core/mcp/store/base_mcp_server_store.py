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

from abc import ABC, abstractmethod
from typing import List, Optional

from agentic_backend.core.agents.agent_spec import MCPServerConfiguration


class BaseMcpServerStore(ABC):
    """
    Minimal interface for persisting MCP server configurations.
    """

    @abstractmethod
    async def save(self, server: MCPServerConfiguration) -> None:
        """
        Persist or replace an MCP server configuration.
        """
        pass

    @abstractmethod
    async def load_all(self) -> List[MCPServerConfiguration]:
        """
        Retrieve all persisted MCP server configurations.
        """
        pass

    @abstractmethod
    async def get(self, server_id: str) -> Optional[MCPServerConfiguration]:
        """
        Retrieve a single MCP server configuration by id.
        """
        pass

    @abstractmethod
    async def delete(self, server_id: str) -> None:
        """
        Delete an MCP server configuration.
        """
        pass

    @abstractmethod
    async def static_seeded(self) -> bool:
        """
        Return True if static servers have already been seeded into the store.
        Used to avoid re-adding statics after they were intentionally deleted.
        """
        pass

    @abstractmethod
    async def mark_static_seeded(self) -> None:
        """
        Mark the store as having seeded static servers.
        """
        pass
