from abc import ABC, abstractmethod

from services.sensor.sensor_structures import SensorSeries, SensorConfigurationSeries

class AbstractSensorService(ABC):
    """
    Interface to retrieve frequency metrics.
    One implementations is provided that uses real data
    stored in some file backends.
    """

    @abstractmethod
    def sweep(self) -> SensorSeries:
        """
        Perform a frequency sweep.
        
        Returns:
            SensorSeries: The frequency sweep series.
        """
        ...
        

class AbstractSensorConfigurationService(ABC):
    """
    Interface to retrieve sensor configurations.
    One implementation is provided that uses real data
    stored in some file backend.
    """

    @abstractmethod
    def get_sensor_configurations(self, neighbourhood_id: str) \
            -> SensorConfigurationSeries:
        """
        Get the list of sensor configurations for all the ships located in the
        provided neighbourhood_id.
        
        Args:
            neighbourhood_id (str): Naval neighbourhood id.

        Returns:
            SensorConfigurationSeries: The object containing sensor configurations data.
        """
        ...