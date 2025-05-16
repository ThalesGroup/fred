from typing import List
from pydantic import BaseModel, Field

class FreqBand(BaseModel):
    lower_freq: int = Field(..., description="Lower frequency band value (MHz)")
    upper_freq: int  = Field(..., description="Upper frequency band value (MHz)")
    
class SensorSeries(BaseModel):
    details: List[FreqBand] = Field(..., description="List of sweep band freq.")
    
    def total_frequency_bands(self) -> int:
        """
        Returns the total number of frequency ranges in the series.
        """
        return len(self.details)

    def use(self) -> List[str]:
        """
        Returns a list of all bands from the details.
        """
        return [[detail.lower_freq, detail.upper_freq] for detail in self.details]


class SensorConfiguration(BaseModel):
    frequency: float = Field(..., description="Sensor frequency emission.")
    bandwidth: float = Field(..., description="Sensor bandwidth emission.")
    protocol: str = Field(..., description="Sensor protocol emission.")

class SensorConfigurationSeries(BaseModel):
    details: List[SensorConfiguration] = Field(..., description="List of sensor configurations.")
    
    def total_sensor_configurations(self) -> int:
        """
        Returns the total number of sensor configurations in the series.
        """
        return len(self.details)

    def sensor_configuration(self) -> List[str]:
        """
        Returns a list of all sensor configurations from the details.
        """
        return [[detail.frequency, detail.bandwidth, detail.protocol] for detail in self.details]