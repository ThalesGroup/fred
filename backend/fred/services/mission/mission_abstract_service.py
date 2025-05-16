from abc import ABC, abstractmethod

from services.mission.mission_structures import MissionSeries

class AbstractMissionService(ABC):
    """
    Interface to retrieve mission information.
    One implementations is provided that uses real data
    stored in some file backends.
    """

    @abstractmethod
    def ship_missions(self) \
            -> MissionSeries:
        """
        Retrieves a list of missions.

        Returns:
            MissionSeries: The object containing the mission data.
        """
        ...