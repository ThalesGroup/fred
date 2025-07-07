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
Module for extracting essential attributes of a service based on its definition.
"""

from typing import Optional, List

from langchain_core.prompts import PromptTemplate
from langfuse.callback import CallbackHandler
from pydantic import BaseModel, Field

from app.application_context import get_structured_chain_for_service


class ServiceEssentials(BaseModel):
    """
    Represents the essential attributes of a service.
    """

    name: str = Field(default="None", description="The name of the service")
    namespace: str = Field(default="None", description="The namespace of the service")
    kind: str = Field(
        default="None",
        description="The type of the service, e.g., ClusterIP, NodePort, LoadBalancer",
    )
    ports: str = Field(
        default="None",
        description="The ports exposed by the service (list separated by commas)",
    )
    selector: str = Field(default="None", description="The selector of the service")
    annotations: str = Field(
        default="None",
        description="The annotations of the service (list separated by commas)",
    )
    labels: str = Field(
        default="None",
        description="The labels of the service (list separated by commas)",
    )

    def __str__(self) -> str:
        """
        Return a string representation of the essential service attributes.

        Returns:
            str: A formatted string containing the service essentials.
        """
        return (
            f"Name: {self.name}\n"
            f"Namespace: {self.namespace}\n"
            f"Kind: {self.kind}\n"
            f"Ports: {self.ports}\n"
            f"Selector: {self.selector}\n"
            f"Annotations: {self.annotations}\n"
            f"Labels: {self.labels}"
        )

    @classmethod
    def from_service_definition(
        cls,
        service_definition: str,
        langfuse_handler: Optional[CallbackHandler] = None,
    ) -> "ServiceEssentials":
        """
        Args:
            service_definition (str): The service definition.
            langfuse_handler (Optional[CallbackHandler]): The LangFuse callback handler.

        Returns:
            ServiceEssentials: An instance containing the essential attributes of the service.
        """
        prompt = PromptTemplate(
            template=(
                "You are an expert in Kubernetes.\n"
                "Based on the following workload YAML definitions:\n\n"
                "{service_definition}\n\n"
                "Please extract and provide the following essentials of the service:\n"
                "- Name of the service\n"
                "- Namespace of the service\n"
                "- Kind of service (e.g., ClusterIP, NodePort, LoadBalancer)\n"
                "- Ports exposed by the service\n"
                "- Selector of the service\n"
                "- Annotations of the service\n"
                "- Labels of the service"
            ),
            input_variables=["service_definition"],
        )

        structured_model = get_structured_chain_for_service("kubernetes", ServiceEssentials)
        chain = prompt | structured_model
        invocation_args = {"service_definition": service_definition}

        if langfuse_handler is not None:
            return chain.invoke(
                invocation_args,
                config={"callbacks": [langfuse_handler]},
            )

        return chain.invoke(invocation_args)

class ServicesEssentials(BaseModel):
    """
    Helper class to store multiple ServiceEssentials objects.
    """
    services_essentials: List[ServiceEssentials] = Field(
        description="The essential attributes of the services associated with the workload"
    )

    @classmethod
    def from_services_definitions(
        cls,
        service_definition: List[str],
        langfuse_handler: Optional[CallbackHandler] = None,
    ) -> "ServicesEssentials":
        """
        Args:
            service_definition (List[str]): The list of service definitions.
            langfuse_handler (Optional[CallbackHandler]): The LangFuse callback handler.
        """
        services_essentials = []
        for definition in service_definition:
            service_essentials = ServiceEssentials.from_service_definition(
                definition, langfuse_handler
            )
            services_essentials.append(service_essentials)

        return cls(services_essentials=services_essentials)
