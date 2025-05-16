from typing import List
from pydantic import BaseModel, Field

class Mission(BaseModel):
    ship: str = Field(..., description="Ship id")
    active: bool = Field(..., description="If the ship is on the mission")
    protocol: str = Field(..., description="Radio protocol used for communication")
    
class MissionSeries(BaseModel):
    details: List[Mission] = Field(..., description="List of ships and wether they are active or not and the protocol they use for communication.")


