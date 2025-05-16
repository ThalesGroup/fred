"""
Module to represent the condensed context of a cluster.
"""

from typing import List

from services.ai.structure.namespace_topology import NamespaceTopology
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
