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
Module for handling commercial off-the-shelf software identification based on workload context that
is composed of the YAML definitions of the workload, configmaps, services, and ingresses.
"""

from typing import Optional

from langchain_core.prompts import PromptTemplate
from langfuse.callback import CallbackHandler
from pydantic import BaseModel, Field
from app.application_context import get_structured_chain_for_service

from app.features.frugal.structure.workload_context import WorkloadContext


class WorkloadId(BaseModel):
    """
    Represents the name of the commercial off-the-shelf software being deployed.
    """

    workload_id: str = Field(
        description="The name of the commercial off-the-shelf software being deployed"
    )

    def __str__(self) -> str:
        """
        Return the name of the commercial off-the-shelf software being deployed.
        """
        return self.workload_id.__str__()

    @classmethod
    def from_workload_context(
        cls,
        workload_context: WorkloadContext,
        langfuse_handler: Optional[CallbackHandler] = None,
    ) -> "WorkloadId":
        """
        Extract the commercial off-the-shelf software name based on the workload context.

        Args:
            workload_context (WorkloadContext): The workload context.
            langfuse_handler (Optional[CallbackHandler]): The LangFuse callback handler.

        Returns:
            workload_id: The extracted commercial off-the-shelf software name.
        """
        prompt = PromptTemplate(
            template=(
                "You are an expert in Kubernetes.\n\n"
                "Based on the following workload definitions:\n\n"
                "{workload_context}\n\n"
                "Please provide the name of the commercial off-the-shelf "
                "software being deployed.\n"
            ),
            input_variables=["workload_definitions"],
        )

        structured_model = get_structured_chain_for_service("kubernetes", WorkloadId)
        chain = prompt | structured_model

        if langfuse_handler is not None:
            return chain.invoke(
                {"workload_context": workload_context},
                config={"callbacks": [langfuse_handler]},
            )

        return chain.invoke({"workload_context": workload_context})
