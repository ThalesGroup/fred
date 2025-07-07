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
Module for extracting a summary of a workload based on its context (YAML definition).
"""

from typing import Optional

from langfuse.callback import CallbackHandler
from pydantic import BaseModel, Field

from fred.application_context import get_model_for_service
from fred.services.ai.structure.workload_context import WorkloadContext


class WorkloadSummary(BaseModel):
    """
    Represents a summary of a workload based on its context (YAML definitions).
    """

    workload_summary: str = Field(
        default="None", description="The summary of the workload"
    )

    def __str__(self) -> str:
        """
        Return the summary of the workload.

        Returns:
            str: The summary of the workload.
        """
        return self.workload_summary.__str__()

    @classmethod
    def from_workload_context(
        cls,
        workload_context: WorkloadContext,
        langfuse_handler: Optional[CallbackHandler] = None,
    ) -> "WorkloadSummary":
        """
        Extract a summary of the workload based on its context (YAML definitions).

        Args:
            workload_context (WorkloadContext): The workload context.
            langfuse_handler (Optional[CallbackHandler]): The LangFuse callback handler.
        """
        model = get_model_for_service("kubernetes")

        prompt = (
                f"You are an expert in Kubernetes.\n\n"
                f"Based on the following workload definitions:\n\n"
                f"{workload_context}\n\n"
                f"Please provide a summary of the workload.\n"
                f"You should highlight the key aspects of the workload, comment on "
                f"the configuration, and provide any other relevant information.\n"
                f"Your response SHOULD be concise.\n"
                f"Start by a title representing the name of the software deployed, then followed "
                f"by structured paragraphs.\n"
                f"You MUST NOT provide a list of informations.\n"
                f"The format of the response should be markdown."
        )

        messages = [{"role": "system", "content": prompt}]

        if langfuse_handler is not None:
            response = model.invoke(
                messages,
                config={"callbacks": [langfuse_handler]},
            )

            return cls(workload_summary=response.content)

        return cls(workload_summary=model.invoke(messages).content)
