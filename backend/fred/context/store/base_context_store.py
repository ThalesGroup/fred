from abc import ABC, abstractmethod
from typing import Optional

class BaseContextStore(ABC):
    @abstractmethod
    def get_context(self, agent_id: str) -> Optional[str]:
        pass

    @abstractmethod
    def set_context(self, agent_id: str, context: str) -> None:
        pass

    @abstractmethod
    def delete_context(self, agent_id: str) -> None:
        pass
