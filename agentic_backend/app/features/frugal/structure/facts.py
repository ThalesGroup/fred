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
Module for the human-provided facts about the system components.
"""

from enum import Enum
from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, Field


class FactType(str, Enum):
    """
    Enumeration for different types of facts.
    """
    DOMAIN = "domain"
    REQUIREMENT = "requirement"
    GOAL = "goal"
    COMPLIANCE = "compliance"
    SECURITY = "security"
    COST = "cost"



class Fact(BaseModel):
    """
    A fact about a component of the system or the system as a whole.

    Attributes:
        user (str): The user who provided the fact.
        date (str): The date the fact was provided.
        title (str): The title of the fact.
        content (str): The content of the fact.
    """

    user: str = Field(description="The user who provided the fact")
    date: datetime = Field(description="The date the fact was provided")
    content: str = Field(description="The content of the fact")
    title: str = Field(description="The title of the fact")
    type: Optional[FactType] = Field(None, description="The type of the fact (optional)")


    def __str__(self) -> str:
        """
        Return the content of the fact.
        """
        representation = (
            f"User: {self.user}\nDate: {self.date}\nContent: {self.content}"
        )
        return representation


class Facts(BaseModel):
    """
    A collection of facts about the system components.

    Attributes:
        facts (List[Fact]): The facts about the system components.
    """

    facts: List[Fact] = Field(
        default_factory=list, description="The facts about the system components"
    )

    def __str__(self) -> str:
        """
        Return a string representation of the facts.

        Returns:
            str: A formatted string containing the facts.
        """
        return "\n\n".join(str(fact) for fact in self.facts) # pylint: disable=not-an-iterable
