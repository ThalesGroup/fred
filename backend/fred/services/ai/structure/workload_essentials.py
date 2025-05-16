"""
Module for extracting essential attributes of the commercial off-the-shelf software being deployed.
"""

from typing import Optional

from langchain_core.prompts import PromptTemplate
from langfuse.callback import CallbackHandler
from pydantic import BaseModel, Field

from fred.application_context import get_structured_chain_for_service


class WorkloadEssentials(BaseModel):
    """
    Represents the essential attributes of the commercial off-the-shelf software being deployed.

    Attributes:
        name (str): The name of the workload.
        namespace (str): The namespace of the workload.
        kind (str): The kind of workload being deployed (e.g., Deployment, StatefulSet).
        container_images (str): The container images associated with the workload.
        version (str): The version of the application (or COTS) being deployed,
                       not the Kubernetes or image version.
        replicas (int): The number of replicas for the workload.
    """

    name: str = Field(default="None", description="The name of the workload")
    namespace: str = Field(default="None", description="The namespace of the workload")
    kind: str = Field(default="None", description="The kind of workload being deployed")
    container_images: str = Field(
        default="None", description="The container images associated with the workload"
    )
    version: str = Field(
        default="None",
        description=(
            "The version of the application (or commercial off-the-shelf software) being deployed, "
            "not the Kubernetes or image version"
        ),
    )
    replicas: int = Field(
        default=1, description="The number of replicas for the workload"
    )

    def __str__(self) -> str:
        """
        Return a string representation of the essential workload attributes.

        Returns:
            str: A formatted string containing the workload essentials.
        """
        return (
            f"Name: {self.name}\n"
            f"Namespace: {self.namespace}\n"
            f"Kind: {self.kind}\n"
            f"Container Images: {self.container_images}\n"
            f"Version: {self.version}\n"
            f"Replicas: {self.replicas}"
        )

    @classmethod
    def from_workload_definition(
        cls,
        workload_definition: str,
        langfuse_handler: Optional[CallbackHandler] = None,
    ) -> "WorkloadEssentials":
        """
        Extract essential attributes of the commercial off-the-shelf software based on the workload
        definition.

        Args:
            workload_definition (str): The workload definition.
            langfuse_handler (Optional[CallbackHandler]): The LangFuse callback handler.

        Returns:
            WorkloadEssentials: An instance containing the extracted essential attributes.
        """
        prompt = PromptTemplate(
            template=(
                "You are an expert in Kubernetes.\n"
                "Based on the following workload YAML definitions:\n\n"
                "{workload_definition}\n\n"
                "Please extract and provide the following essentials of the deployed software:\n"
                "- Name of the workload\n"
                "- Namespace\n"
                "- Kind of workload (e.g., Deployment, StatefulSet)\n"
                "- Container image\n"
                "- Version of the application (not Kubernetes or image version)\n"
                "- Number of replicas\n\n"
                "Provide the information in a structured JSON format with the keys: "
                "`name`, `namespace`, `kind`, `container_images`, `version`, `replicas`."
            ),
            input_variables=["workload_definition"],
        )

        structured_model = get_structured_chain_for_service("kubernetes", WorkloadEssentials)
        chain = prompt | structured_model
        invocation_args = {"workload_definition": workload_definition}

        if langfuse_handler is not None:
            return chain.invoke(
                invocation_args,
                config={"callbacks": [langfuse_handler]},
            )

        return chain.invoke(invocation_args)
