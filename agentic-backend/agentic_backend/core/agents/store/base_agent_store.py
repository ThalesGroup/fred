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


class BaseAgentStore(ABC):
    """
    Interface for persistent storage of agent metadata (not instances).
    """

    @abstractmethod
    async def save(
        self,
        settings: AgentSettings,
        tuning: AgentTuning,
    ) -> None:
        """
        Persist an agent's settings.
        """
        pass

    @abstractmethod
    async def load_all(self) -> List[AgentSettings]:
        """
        Retrieve all persisted agent definitions.
        """
        pass

    @abstractmethod
    async def get(
        self,
        agent_id: str,
    ) -> Optional[AgentSettings]:
        """
        Retrieve a single agent definition by ID.
        """
        pass

    @abstractmethod
    async def delete(
        self,
        agent_id: str,
    ) -> None:
        """
        Delete an agent's settings.

        :param agent_id: The ID of the agent to delete.
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
