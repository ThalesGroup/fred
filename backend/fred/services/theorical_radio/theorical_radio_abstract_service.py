from abc import ABC, abstractmethod

from services.theorical_radio.theorical_radio_structures import TheoricalRadioSeries

class AbstractTheoricalRadioService(ABC):
    """
    Interface to retrieve information on theorical radio data.
    One implementations is provided that uses real data
    stored in some file backends.
    """

    @abstractmethod
    def radio_data(self) \
            -> TheoricalRadioSeries:
        """
        Retrieves a list of radio data.

        Returns:
            TheoricalRadioSeries: The object containing the radio data.
        """
        ...