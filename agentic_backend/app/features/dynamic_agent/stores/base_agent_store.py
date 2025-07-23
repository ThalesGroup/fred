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
from app.features.dynamic_agent.structures import MCPAgentRequest

class BaseDynamicAgentStore(ABC):
    """
    Interface for persistent storage of dynamically created agents.
    """

    @abstractmethod
    def save(self, req: MCPAgentRequest) -> None:
        """
        Persist an agent request.
        """
        pass

    @abstractmethod
    def load_all(self) -> List[MCPAgentRequest]:
        """
        Retrieve all persisted agent requests.
        """
        pass

    @abstractmethod
    def get(self, name: str) -> Optional[MCPAgentRequest]:
        """
        Retrieve a single agent request by name.
        """
        pass
