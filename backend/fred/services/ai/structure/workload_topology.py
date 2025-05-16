"""
Module that defines the structure of an overall workload topology.
"""

import textwrap
from pydantic import BaseModel, Field

from services.ai.structure.facts import Facts
from services.ai.structure.ingress_essentials import IngressesEssentials
from services.ai.structure.service_essentials import ServicesEssentials
from services.ai.structure.workload_essentials import WorkloadEssentials
from services.ai.structure.workload_id import WorkloadId
from services.ai.structure.workload_summary import WorkloadSummary


class WorkloadTopology(BaseModel):
    """
    Represents the overall topology of a workload.
    """
    workload_id: WorkloadId = Field(
        description="The name of the commercial off-the-shelf software being deployed"
    )
    workload_essentials: WorkloadEssentials = Field(
        description="The essential attributes of the workload"
    )
    workload_summary: WorkloadSummary = Field(
        description="The summary of the Workload"
    )
    services_essentials: ServicesEssentials = Field(
        description="The essential attributes of the services associated with the workload"
    )
    ingresses_essentials: IngressesEssentials = Field(
        description="The essential attributes of the ingresses associated with the workload"
    )
    facts: Facts = Field(
        description="The facts about the system components"
    )

    def __str__(self) -> str:
        """
        Return a string representation of the workload topology.

        Returns:
            str: A formatted string containing the workload topology.
        """
        representation = ""

        # Present the software and version.
        representation += f"software: {self.workload_id.__str__()}\n"
        representation += f"version: {self.workload_essentials.version}\n" # pylint: disable=E1101

        # Present general Kubernetes workload information.
        representation += (
            f"name: {self.workload_essentials.name}\n" # pylint: disable=E1101
            f"kind: {self.workload_essentials.kind}\n" # pylint: disable=E1101
            f"namespace: {self.workload_essentials.namespace}\n" # pylint: disable=E1101
            f"images: {self.workload_essentials.container_images}\n" # pylint: disable=E1101
            f"replicas: {self.workload_essentials.replicas}\n" # pylint: disable=E1101
        )

        # Present the services.
        representation += "services:\n"
        for service in self.services_essentials.services_essentials: # pylint: disable=E1101
            representation += f"  - {service.name}:\n"
            representation += f"      kind: {service.kind}\n"
            representation += f"      ports: {service.ports}\n"

        # Present the ingresses.
        representation += "ingresses:\n"
        for ingress in self.ingresses_essentials.ingresses_essentials: # pylint: disable=E1101
            representation += f"  - {ingress.name}:\n"
            representation += f"      hosts: {ingress.hosts}\n"
            representation += f"      paths: {ingress.paths}\n"
            representation += f"      tls_enabled: {ingress.tls_enabled}\n"
            representation += f"      service_names: {ingress.service_names}\n"

        # Present the workload summary.
        representation += "summary: |\n"
        representation += textwrap.indent(
            textwrap.fill(self.workload_summary.__str__(), width=80),
            prefix='  '
        )
        representation += "\n"

        # Present the facts.
        if self.facts.facts:
            representation += "facts:\n"
            for fact in self.facts.facts: # pylint: disable=E1101
                representation += f"  - {fact.user}, {fact.date}: |\n"
                representation += textwrap.indent(
                    textwrap.fill(fact.content, width=76),
                    prefix='      '
                )
                representation += "\n"

        return representation
