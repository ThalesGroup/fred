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

"""
Module for the human-provided scalings about the system components.
"""

from typing import List
from datetime import datetime

from pydantic import BaseModel, Field


class Scaling(BaseModel):
    """
    A scaling about a component of the system or the system as a whole.

    Attributes:
        user (str): The user who provided the scaling.
        date (str): The date the scaling was provided.
        title (str): The title of the scaling.
        content (str): The content of the scaling.
    """

    user: str = Field(description="The user who provided the scaling")
    date: datetime = Field(description="The date the scaling was provided")
    content: str = Field(description="The content of the scaling")
    title: str = Field(description="The title of the scaling")

    def __str__(self) -> str:
        """
        Return the content of the scaling.
        """
        representation = (
            f"User: {self.user}\nDate: {self.date}\nContent: {self.content}"
        )
        return representation


class Scalings(BaseModel):
    """
    A collection of scalings about the system components.

    Attributes:
        scalings (List[scaling]): The scalings about the system components.
    """

    scalings: List[Scaling] = Field(
        default_factory=list, description="The scalings about the system components"
    )

    def __str__(self) -> str:
        """
        Return a string representation of the scalings.

        Returns:
            str: A formatted string containing the scalings.
        """
        return "\n\n".join(str(scaling) for scaling in self.scalings)  # pylint: disable=not-an-iterable
