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
Module that defines the structure of a cluster topology.
"""

from pydantic import BaseModel, Field
import textwrap

from services.ai.structure.facts import Facts
from services.ai.structure.cluster_context import ClusterContext
from services.ai.structure.cluster_summary import ClusterSummary


class ClusterTopology(BaseModel):
    """
    Represents the overall topology of a cluster.
    """
    cluster_context: ClusterContext = Field(
        description="The context of the cluster"
    )
    cluster_summary: ClusterSummary = Field(
        description="The summary of the cluster"
    )
    facts: Facts = Field(
        description="The facts about the cluster"
    )

    def __str__(self) -> str:
        """
        Return a string representation of the cluster topology.

        Returns:
            str: A formatted string containing the cluster topology.
        """
        representation = f"{self.cluster_context.__str__()}\n"
        
        representation += "cluster summary: |\n"
        representation += textwrap.indent(
            textwrap.fill(self.cluster_summary.__str__().replace('\n', ' '), width=80),
            prefix='  '
        )
        representation += "\n\n"

        if self.facts.facts:
            representation += f"cluster facts:\n"
            for fact in self.facts.facts: # pylint: disable=E1101
                representation += f"  - {fact.user}, {fact.date}: |\n"
                representation += textwrap.indent(
                    textwrap.fill(fact.content, width=76),
                    prefix='      '
                )

        return representation
