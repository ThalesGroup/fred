from abc import ABC, abstractmethod

from services.theater_analysis.theater_analysis_structures import TheaterAnalysisSeries

class AbstractTheaterAnalysisService(ABC):
    """
    Interface to retrieve a ship location based on the radio protocol it uses.
    One implementations is provided that uses real data
    stored in some file backends.
    """

    @abstractmethod
    def theater_analysis(self) \
            -> TheaterAnalysisSeries:
        """
        Retrieves the ship location information from the specified protocol.

        Returns:
            TheaterAnalysisSeries: The object containing ship location information.
        """
        ...