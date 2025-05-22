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


class Plan(BaseModel):
    """Series of steps to follow."""

    steps: List[str] = Field(
        description="Different steps to follow, MUST be in sorted order."
    )

    def __str__(self):
        """
        Return a string representation of the plan.
        """
        return "\n".join(f"{i+1}. {step}" for i, step in enumerate(self.steps))
