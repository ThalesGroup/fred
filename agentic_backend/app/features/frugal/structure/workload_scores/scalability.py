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
Module for generating the scalability score of a workload.
"""

from typing import Optional

from langchain_core.prompts import PromptTemplate
from langfuse.callback import CallbackHandler
from pydantic import BaseModel, Field
from app.application_context import get_structured_chain_for_service

from app.features.frugal.structure.workload_context import WorkloadContext


class ScalabilityScore(BaseModel):
    """
    Represents the scalability score of a workload.

    The scalability score is a numerical grade on a scale of 0 to 10,
    where 0 represents the worst scalability optimization and 10 represents
    the best possible scalability performance.
    """

    score: float = Field(
        default=None,
        description="The scalability score, a grade on a scale of 0 to 10",
    )
    reason: str = Field(
        default=None, description="An explanation of the scalability score"
    )

    def __str__(self) -> str:
        """
        Return a string representation of the scalability score.

        Returns:
            str: A formatted string containing the scalability score.
        """
        return f"Scalability Score: {self.score}\nReason: {self.reason}"

    @classmethod
    def from_workload_context(
        cls,
        workload_context: WorkloadContext,
        langfuse_handler: Optional[CallbackHandler] = None,
    ) -> "ScalabilityScore":
        """
        Extract the scalability score based on the workload context.

        Args:
            workload_context (WorkloadContext): The workload context.
            langfuse_handler (Optional[CallbackHandler]): The LangFuse callback handler.

        Returns:
            ScalabilityScore: The extracted scalability score.
        """
        prompt = PromptTemplate(
            template=(
                "You are an expert in Kubernetes and cloud-native applications.\n\n"
                "Based on the following workload definitions:\n\n"
                "{workload_context}\n\n"
                "Please provide the scalability score for the workload.\n"
                "The score should be between 0 and 10 (higher the better).\n"
                "It should represent how well the application is optimized for scalability.\n"
                "Also, provide a concise explanation of why you provided that score considering "
                "the software architecture, its configuration, and technical context."
            ),
            input_variables=["workload_context"],
        )

        structured_model = get_structured_chain_for_service(
            "kubernetes", ScalabilityScore
        )
        chain = prompt | structured_model
        if langfuse_handler is not None:
            return chain.invoke(
                {"workload_context": workload_context},
                config={"callbacks": [langfuse_handler]},
            )

        return chain.invoke({"workload_context": workload_context})
