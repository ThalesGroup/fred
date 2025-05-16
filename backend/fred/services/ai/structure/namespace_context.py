"""
Module to represent the context of a namespace.
"""

from typing import List, Optional

from services.ai.structure.workload_topology import WorkloadTopology
from pydantic import BaseModel, Field


class NamespaceContext(BaseModel):
    """
    Represents the context of a namespace.
    """

    name: str = Field(default="None", description="The name of the namespace")
    workload_topologies: List[WorkloadTopology] = Field(
        description="The topologies of the workloads in the namespace"
    )
    resource_quota: Optional[str] = Field(
        default=None, description="The resource quota of the namespace"
    )
    limitrange_resource: Optional[str] = Field(
        default=None, description="The limit range resource of the namespace"
    )

    def __str__(self) -> str:
        """
        Return a string representation of the namespace context.
        """
        representation = f"namespace: {self.name}\n"

        if self.resource_quota is not None:
            representation += f"resource quota: {self.resource_quota}\n"

        if self.limitrange_resource is not None:
            representation += f"limitrange resource: {self.limitrange_resource}\n"

        representation += "workload topologies:\n"
        for workload_topology in self.workload_topologies:
            representation += f"---\n{workload_topology.__str__()}\n"

        return representation
