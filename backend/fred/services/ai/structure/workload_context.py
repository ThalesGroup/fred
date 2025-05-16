"""
Module to represent the context of a workload.
"""

from typing import Optional

from pydantic import BaseModel, Field


class WorkloadContext(BaseModel):
    """
    Represents the YAML context of a workload.
    """

    workload_yaml: str = Field(
        description="The YAML definition of the workload"
    )
    configmaps_yaml: Optional[str] = Field(
        default=None, description="The YAML definition of the configmaps"
    )
    services_yaml: Optional[str] = Field(
        default=None, description="The YAML definition of the services"
    )
    ingresses_yaml: Optional[str] = Field(
        default=None, description="The YAML definition of the ingresses"
    )

    def __str__(self) -> str:
        """
        Return a string representation of the workload context.
        """
        representation = f"Workload YAML:\n\n{self.workload_yaml}\n\n"
        if self.configmaps_yaml:
            representation += f"Configmaps YAML:\n\n{self.configmaps_yaml}\n\n"
        if self.services_yaml:
            representation += f"Services YAML:\n\n{self.services_yaml}\n\n"
        if self.ingresses_yaml:
            representation += f"Ingresses YAML:\n\n{self.ingresses_yaml}"

        return representation
