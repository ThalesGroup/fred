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
Module that defines the structure of an overall namespace topology.
"""

from pydantic import BaseModel, Field
import textwrap

from app.features.frugal.structure.facts import Facts
from app.features.frugal.structure.namespace_context import NamespaceContext
from app.features.frugal.structure.namespace_summary import NamespaceSummary


class NamespaceTopology(BaseModel):
    """
    Represents the overall topology of a namespace.
    """
    namespace_context: NamespaceContext = Field(
        description="The context of the namespace"
    )
    namespace_summary: NamespaceSummary = Field(
        description="The summary of the namespace"
    )
    facts: Facts = Field(
        description="The facts about the namespace"
    )

    def __str__(self) -> str:
        """
        Return a string representation of the namespace topology.

        Returns:
            str: A formatted string containing the namespace topology.
        """
        representation = f"{self.namespace_context.__str__()}\n"

        representation += "namespace summary: |\n"
        representation += textwrap.indent(
            textwrap.fill(self.namespace_summary.__str__().replace('\n', ' '), width=80),
            prefix='  '
        )

        if self.facts.facts:
            representation += f"namespace facts:\n"
            for fact in self.facts.facts: # pylint: disable=E1101
                representation += f"  - {fact.user}, {fact.date}: |\n"
                representation += textwrap.indent(
                    textwrap.fill(fact.content, width=76),
                    prefix='      '
                )

        return representation
