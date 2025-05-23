# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import List
from pydantic import BaseModel, Field

class Mission(BaseModel):
    ship: str = Field(..., description="Ship id")
    active: bool = Field(..., description="If the ship is on the mission")
    protocol: str = Field(..., description="Radio protocol used for communication")
    
class MissionSeries(BaseModel):
    details: List[Mission] = Field(..., description="List of ships and wether they are active or not and the protocol they use for communication.")


