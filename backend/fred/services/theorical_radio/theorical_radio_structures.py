from typing import List
from pydantic import BaseModel, Field

class RadioData(BaseModel):
    type: str = Field(..., description="Ship id")
    description: str = Field(..., description="If the ship is on the mission")
    frequency: str = Field(..., description="Radio protocol used for communication")
    mode: str = Field(..., description="Radio protocol used for communication")
    modulation: str = Field(..., description="Radio protocol used for communication")
    bandwidth: str = Field(..., description="Radio protocol used for communication")
    location: str = Field(..., description="Radio protocol used for communication")
    min_freq: float = Field(..., description="Radio protocol used for communication")
    max_freq: float = Field(..., description="Radio protocol used for communication")
    
class TheoricalRadioSeries(BaseModel):
    details: List[RadioData] = Field(..., description="List of ships and wether they are active or not and the protocol they use for communication.")


