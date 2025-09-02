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

from typing import Optional
from pydantic import BaseModel, Field


class AgenticFlow(BaseModel):
    """
    Agentic flow structure
    """

    name: Optional[str] = Field(default=None, description="Name of the agentic flow")
    role: str = Field(description="Human-readable role of the agentic flow")
    nickname: Optional[str] = Field(
        default=None, description="Human-readable nickname of the agentic flow"
    )
    description: str = Field(
        description="Human-readable description of the agentic flow"
    )
    icon: Optional[str] = Field(description="Icon of the agentic flow")
    experts: Optional[list[str]] = Field(
        description="List of experts in the agentic flow"
    )
    tag: Optional[str] = Field(description="Human-readable tag of the agentic flow")
