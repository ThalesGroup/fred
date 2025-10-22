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


class BaseAgentStore(ABC):
    """
    Interface for persistent storage of agent metadata (not instances).
    """

    @abstractmethod
    def save(self, settings: AgentSettings) -> None:
        """
        Persist an agent's settings.
        """
        pass

    @abstractmethod
    def load_all(self) -> List[AgentSettings]:
        """
        Retrieve all persisted agent definitions.
        """
        pass

    @abstractmethod
    def get(self, name: str) -> Optional[AgentSettings]:
        """
        Retrieve a single agent definition by name.
        """
        pass

    @abstractmethod
    def delete(self, name: str) -> None:
        """
        Delete an agent by name.
        """
        pass
