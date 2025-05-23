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
Module for extracting essential attributes of an ingress based on its definition.
"""

from typing import Optional, List

from langchain_core.prompts import PromptTemplate
from langfuse.callback import CallbackHandler
from pydantic import BaseModel, Field

from fred.application_context import get_structured_chain_for_service


class IngressEssentials(BaseModel):
    """
    Represents the essential attributes of an ingress.
    """

    name: str = Field(default="None", description="The name of the ingress")
    namespace: str = Field(default="None", description="The namespace of the ingress")
    hosts: str = Field(
        default="None",
        description="The hosts associated with the ingress (list separated by commas)",
    )
    tls_enabled: str = Field(
        default="None",
        description="Whether TLS is enabled for the ingress (true/false)",
    )
    paths: str = Field(
        default="None",
        description="The paths associated with the ingress (list separated by commas)",
    )
    service_names: str = Field(
        default="None",
        description="The names of services associated with the ingress (list separated by commas)",
    )
    annotations: str = Field(
        default="None",
        description="The annotations of the ingress (list separated by commas)",
    )
    labels: str = Field(
        default="None",
        description="The labels of the ingress (list separated by commas)",
    )

    def __str__(self) -> str:
        """
        Return a string representation of the essential ingress attributes.

        Returns:
            str: A formatted string containing the ingress essentials.
        """
        return (
            f"Name: {self.name}\n"
            f"Namespace: {self.namespace}\n"
            f"Hosts: {self.hosts}\n"
            f"TLS Enabled: {self.tls_enabled}\n"
            f"Paths: {self.paths}\n"
            f"Service Names: {self.service_names}\n"
            f"Annotations: {self.annotations}\n"
            f"Labels: {self.labels}"
        )

    @classmethod
    def from_ingress_definition(
        cls,
        ingress_definition: str,
        langfuse_handler: Optional[CallbackHandler] = None,
    ) -> "IngressEssentials":
        """
        Args:
            ingress_definition (str): The ingress definition.
            langfuse_handler (Optional[CallbackHandler]): The LangFuse callback handler.

        Returns:
            IngressEssentials: An instance containing the essential attributes of the ingress.
        """
        prompt = PromptTemplate(
            template=(
                "You are an expert in Kubernetes.\n"
                "Based on the following workload YAML definitions:\n\n"
                "{ingress_definition}\n\n"
                "Please extract and provide the following essentials of the ingress:\n"
                "- Name of the ingress\n"
                "- Namespace of the ingress\n"
                "- Hosts associated with the ingress\n"
                "- Whether TLS is enabled for the ingress\n"
                "- Paths associated with the ingress\n"
                "- Names of services associated with the ingress\n"
                "- Annotations of the ingress\n"
                "- Labels of the ingress\n\n"
                "Provide the information in a structured JSON format with the keys: "
                "'name', 'namespace', 'hosts', 'tls_enabled', 'paths', "
                "'service_names', 'annotations', 'labels'"
            ),
            input_variables=["ingress_definition"],
        )

        structured_model = get_structured_chain_for_service("kubernetes", IngressEssentials)
        chain = prompt | structured_model

        invocation_args = {"ingress_definition": ingress_definition}

        if langfuse_handler is not None:
            return chain.invoke(
                invocation_args,
                config={"callbacks": [langfuse_handler]},
            )

        return chain.invoke(invocation_args)

class IngressesEssentials(BaseModel):
    """
    Helper class to store multiple IngressEssentials objects.
    """
    ingresses_essentials: List[IngressEssentials] = Field(
        description="The essential attributes of the ingresses associated with the workload"
    )

    @classmethod
    def from_ingresses_definitions(
        cls,
        ingress_definition: List[str],
        langfuse_handler: Optional[CallbackHandler] = None,
    ) -> "IngressesEssentials":
        """
        Args:
            ingress_definition (List[str]): The list of ingress definitions.
            langfuse_handler (Optional[CallbackHandler]): The LangFuse callback handler.
        """
        ingresses_essentials = []
        for definition in ingress_definition:
            ingress_essentials = IngressEssentials.from_ingress_definition(
                definition, langfuse_handler
            )
            ingresses_essentials.append(ingress_essentials)

        return cls(ingresses_essentials=ingresses_essentials)
