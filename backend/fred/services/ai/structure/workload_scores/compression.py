"""
Module for generating the compression score of a workload.
"""

from typing import Optional

from langchain_core.prompts import PromptTemplate
from langfuse.callback import CallbackHandler
from pydantic import BaseModel, Field
from fred.application_context import get_structured_chain_for_service

from services.ai.structure.workload_context import WorkloadContext

class CompressionScore(BaseModel):
    """
    Represents the compression score of a workload.

    The compression score is a numerical grade on a scale of 0 to 10, 
    where 0 represents the worst compression efficiency and 10 represents 
    the best possible compression performance.
    """
    score: float = Field(
        default=None,
        description="The compression score, a grade on a scale of 0 to 10",
    )
    reason: str = Field(default=None, description="An explanation of the compression score")


    def __str__(self) -> str:
        """
        Return a string representation of the compression score.

        Returns:
            str: A formatted string containing the compression score.
        """
        return (
            f"Compression Score: {self.score}\n"
            f"Reason: {self.reason}"
        )

    @classmethod
    def from_workload_context(
        cls,
        workload_context: WorkloadContext,
        langfuse_handler: Optional[CallbackHandler] = None,
    ) -> "CompressionScore":
        """
        Extract the compression score based on the workload context.
        
        Args:
            workload_context (WorkloadContext): The workload context.
            langfuse_handler (Optional[CallbackHandler]): The LangFuse callback handler.

        Returns:
            compression_score: The extracted compression score.
        """
        prompt = PromptTemplate(
            template=(
                "You are an expert in Kubernetes and cloud-native applications.\n\n"
                "Based on the following workload definitions:\n\n"
                "{workload_context}\n\n"
                "Please provide the compression score for the workload.\n"
                "The score should be between 0 and 10 (higher the better).\n"
                "It should represent how well the application is optimized for compression.\n"
                "Also, provide a concise explanation of why you provided that score considering "
                "the software nature, its configuration and technical context."
            ),
            input_variables=["workload_context"],
        )

        structured_model = get_structured_chain_for_service("kubernetes", CompressionScore)
        chain = prompt | structured_model
        if langfuse_handler is not None:
            return chain.invoke(
                {"workload_context": workload_context},
                config={"callbacks": [langfuse_handler]},
            )

        return chain.invoke({"workload_context": workload_context})
