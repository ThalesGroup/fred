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
Module to represent the condensed context of a cluster.
"""

from typing import List

from fred.services.ai.structure.namespace_topology import NamespaceTopology
from pydantic import BaseModel, Field


class ClusterContext(BaseModel):
    """
    Represents the condensed context of a cluster.
    """

    name: str = Field(default="None", description="The name of the cluster")
    namespace_topologies: List[NamespaceTopology] = Field(
        description="The topologies of the namespaces in the cluster"
    )

    def __str__(self) -> str:
        """
        Return a string representation of the cluster context.
        """
        representation = f"cluster: {self.name}\n\n"

        representation += "namespace topologies:\n\n"
        for namespace_topology in self.namespace_topologies:
            representation += f"------\n------\n\n{namespace_topology.__str__()}\n\n"

        return representation
