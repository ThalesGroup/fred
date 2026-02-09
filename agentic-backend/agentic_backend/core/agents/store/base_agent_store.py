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

from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.agent_spec import AgentTuning

SCOPE_GLOBAL = "GLOBAL"
SCOPE_USER = "USER"


class BaseAgentStore(ABC):
    """
    Interface for persistent storage of agent metadata (not instances).
    """

    @abstractmethod
    async def save(
        self,
        settings: AgentSettings,
        tuning: AgentTuning,
        scope: str = SCOPE_GLOBAL,
        scope_id: Optional[str] = None,
    ) -> None:
        """
        Persist an agent's settings.
        """
        pass

    @abstractmethod
    async def load_by_scope(
        self,
        scope: str,
        scope_id: Optional[str] = None,
    ) -> List[AgentSettings]:
        """
        Retrieve all persisted agent definitions for a specific scope.

        :param scope: The scope to load (e.g., 'GLOBAL', 'USER').
        :param scope_id: The specific ID for the scope (e.g., a user ID).
        :return: A list of AgentSettings objects for the given scope.
        """
        pass

    @abstractmethod
    async def load_all_global_scope(self) -> List[AgentSettings]:
        """
        Retrieve all persisted agent definitions.
        """
        pass

    @abstractmethod
    async def get(
        self,
        name: str,
        scope: str = SCOPE_GLOBAL,
        scope_id: Optional[str] = None,
    ) -> Optional[AgentSettings]:
        """
        Retrieve a single agent definition by name for a specific scope.
        """
        pass

    @abstractmethod
    async def delete(
        self,
        name: str,
        scope: str = SCOPE_GLOBAL,
        scope_id: Optional[str] = None,
    ) -> None:
        """
        Delete an agent's settings for a specific scope.
        - Admin action: delete with scope=GLOBAL.
        - User action: delete with scope=USER and user_id.

        :param name: The name of the agent to delete.
        :param scope: The scope of the settings to delete.
        :param scope_id: The ID of the scope (e.g., user ID).
        """
        pass

    @abstractmethod
    async def static_seeded(self) -> bool:
        """
        True when static agents have already been seeded into the persistent store.
        Used to avoid re-seeding deleted static agents after a restart.
        """
        pass

    @abstractmethod
    async def mark_static_seeded(self) -> None:
        """
        Mark the store as having seeded static agents.
        """
        pass


class AgentNotFoundError(Exception):
    """Raised when an agent is not found."""

    pass
