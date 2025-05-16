from typing import List
from pydantic import BaseModel, Field

class ShipSignalLocation(BaseModel):
    frequency: float = Field(..., description="")
    bandwidth: float = Field(..., description="")
    protocol: str = Field(..., description="")
    location: str = Field(..., description="")
    
class TheaterAnalysisSeries(BaseModel):
    details: List[ShipSignalLocation] = Field(..., description="Abnoral ship information.")
    
    def total_theater_analysiss(self) -> int:
        """
        Returns the total number of ship locations in the series.
        """
        return len(self.details)

    def theater_analysiss(self) -> List[str]:
        """
        Returns a list of all ship locations from the details.
        """
        return [detail.location for detail in self.details]
    
# Mission Tool
class Mission(BaseModel):
    ship: str = Field(..., description="Ship id")
    active: bool = Field(..., description="If the ship is on the mission")
    protocol: str = Field(..., description="Radio protocol used for communication")
    
class MissionSeries(BaseModel):
    details: List[Mission] = Field(..., description="List of ships and wether they are active or not and the protocol they use for communication.")


# Sensor data detection Tool
class DetectedData(BaseModel):
    id: int = Field(..., description="Measurement id")
    type: str = Field(..., description="Signal type")
    frequency: float = Field(..., description="Measured frequency")
    bandwidth: float = Field(..., description="Measured bandwidth")
    level: int = Field(..., description="Measured decibel level")
    azimuth: int = Field(..., description="Measured azimuth angle")
    modulation: str = Field(..., description="Signal modulation")
    protocol: str = Field(..., description="Signal communication protocol")
    beginning_s: int = Field(..., description="Timestamp describing the beginning of the detected communication")
    duration_ms: int = Field(..., description="Communication duration")
    location: str = Field(..., description="Location of he ship that emitted the signal")
    
class DetectedDataSeries(BaseModel):
    details: List[DetectedData] = Field(..., description="List of discrete measurements detected offshore.")



