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
Module for generating workload scores.
"""

from typing import Optional

from langfuse.callback import CallbackHandler
from pydantic import BaseModel, Field

from services.ai.structure.workload_context import WorkloadContext
from services.ai.structure.workload_scores.compression import CompressionScore
from services.ai.structure.workload_scores.cpu import CpuScore
from services.ai.structure.workload_scores.io import IoScore
from services.ai.structure.workload_scores.ram import RamScore
from services.ai.structure.workload_scores.scalability import ScalabilityScore


class WorkloadScores(BaseModel):
    """
    Represents the scores of a workload on different aspects.

    Attributes:
        cpu (float): The CPU score.
        ram (float): The RAM score.
        io (float): The IO score.
        scalability (float): The scalability score.
        compression (float): The compression score.
    """

    cpu: CpuScore = Field(default=None, description="The CPU score")
    ram: RamScore = Field(default=None, description="The RAM score")
    io: IoScore = Field(default=None, description="The IO score")
    scalability: ScalabilityScore = Field(
        default=None, description="The scalability score"
    )
    compression: CompressionScore = Field(
        default=None, description="The compression score"
    )

    def __init__( # pylint: disable=R0913, R0917
        self,
        cpu: CpuScore,
        ram: RamScore,
        io: IoScore,
        scalability: ScalabilityScore,
        compression: CompressionScore,
    ) -> None:
        """
        Initialize the WorkloadScores class.

        Args:
            cpu (CpuScore): The CPU score.
            ram (RamScore): The RAM score.
            io (IoScore): The IO score.
            scalability (ScalabilityScore): The scalability score.
            compression (CompressionScore): The compression score.
        """
        super().__init__(
            cpu=cpu, ram=ram, io=io, scalability=scalability, compression=compression
        )

    def __str__(self) -> str:
        """
        Return a string representation of the workload scores.

        Returns:
            str: A formatted string containing the workload scores.
        """
        return (
            f"CPU Score: {self.cpu}\n"
            f"RAM Score: {self.ram}\n"
            f"IO Score: {self.io}\n"
            f"Scalability Score: {self.scalability}\n"
            f"Compression Score: {self.compression}"
        )

    @classmethod
    def from_workload_context(
        cls,
        workload_context: WorkloadContext,
        langfuse_handler: Optional[CallbackHandler] = None,
    ) -> "WorkloadScores":
        """
        Extract the scores of a workload based on the workload context.

        Args:
            workload_context (WorkloadContext): The workload context.
            langfuse_handler (Optional[CallbackHandler]): The LangFuse callback handler.

        Returns:
            WorkloadScores: The extracted scores of the workload.
        """
        cpu = CpuScore.from_workload_context(workload_context, langfuse_handler)
        ram = RamScore.from_workload_context(workload_context, langfuse_handler)
        io = IoScore.from_workload_context(workload_context, langfuse_handler)
        scalability = ScalabilityScore.from_workload_context(
            workload_context, langfuse_handler
        )
        compression = CompressionScore.from_workload_context(
            workload_context, langfuse_handler
        )

        return cls(
            cpu=cpu, ram=ram, io=io, scalability=scalability, compression=compression
        )
