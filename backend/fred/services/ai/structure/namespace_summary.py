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
Module for extracting a summary of a namespace based on the topology of its workloads.
"""

from typing import Optional

from langchain_core.prompts import PromptTemplate
from langfuse.callback import CallbackHandler
from pydantic import BaseModel, Field

from fred.application_context import get_structured_chain_for_service
from services.ai.structure.namespace_context import NamespaceContext


class NamespaceSummary(BaseModel):
    """
    Represents a summary of a namespace based on its context.
    """

    namespace_summary: str = Field(
        default="None", description="The summary of the namespace"
    )

    def __str__(self) -> str:
        """
        Return the summary of the namespace.

        Returns:
            str: The summary of the namespace.
        """
        return self.namespace_summary.__str__()

    @classmethod
    def from_namespace_context(
        cls,
        namespace_context: NamespaceContext,
        langfuse_handler: Optional[CallbackHandler] = None,
    ) -> "NamespaceSummary":
        """
        Extract a summary of the namespace based on its context.

        Args:
            namespace_context (NamespaceContext): The context of the namespace.
            langfuse_handler (Optional[CallbackHandler]): The LangFuse callback handler.
        """
        prompt = PromptTemplate(
            template=(
                "You are an expert in Kubernetes.\n"
                "Your role is to analyze a namespace based on its context.\n\n"
                "Here are some information about the attributes of the namespace and the "
                "workloads it contains:\n\n"
                "{namespace_context}\n\n"
                "Please provide a summary of the namespace.\n"
                "You should highlight the key aspects, commenting on potential relationships "
                "between the workloads, and providing any other relevant information like the "
                "purpose of this kind of setup.\n"
                "Your response should be concise and provided in markdown format.\n"
                "Start by a title representing the name of the namespace, then followed by "
                "structured paragraphs.\n"
                "You MUST NOT provide a list of informations.\n"
                "Provide the summary in a structured JSON format with the key: "
                "`namespace_summary`."
            ),
            input_variables=["namespace_context"],
        )

        structured_model = get_structured_chain_for_service("kubernetes", NamespaceSummary)
        chain = prompt | structured_model

        invocation_args = {"namespace_context": namespace_context}

        if langfuse_handler is not None:
            return chain.invoke(
                invocation_args,
                config={"callbacks": [langfuse_handler]},
            )

        return chain.invoke(invocation_args)
