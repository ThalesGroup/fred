
from abc import ABC, abstractmethod
from typing import Optional

class BaseFeedbackStore(ABC):
    @abstractmethod
    def get_feedback(self, agent_id: str) -> Optional[str]:
        pass

    @abstractmethod
    def set_feedback(self, agent_id: str, feedback: str) -> None:
        pass

    @abstractmethod
    def delete_feedback(self, agent_id: str) -> None:
        pass
