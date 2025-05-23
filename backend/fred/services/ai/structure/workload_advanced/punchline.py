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
Module to represent advanced information about a Punchline workload.
"""

from typing import Optional, Literal

from langchain_core.prompts import PromptTemplate
from langfuse.callback import CallbackHandler
from pydantic import Field, BaseModel
from fred.application_context import get_structured_chain_for_service

from services.ai.structure.workload_context import WorkloadContext


class PunchlineAdvanced(BaseModel):
    """
    Represents advanced informations about a Punchline workload.
    """
    type: Literal["punchline"] = Field(
        default="punchline", description="The type of workload, used for discriminated union")
    pipeline_workers: Optional[int] = Field(
        default=None, description="Number of workers in the Punchline"
    )
    pipeline_batch_size: Optional[int] = Field(
        default=None, description="Batch size in the Punchline"
    )
    pipeline_batch_delay: Optional[int] = Field(
        default=None, description="Batch delay in the Punchline"
    )
    heap_size: Optional[str] = Field(default=None, description="Heap size for the Punchline")
    log_level: Optional[str] = Field(default=None, description="Log level for the Punchline")
    input_plugin: Optional[str] = Field(
        default=None, description="Input plugin for the Punchline"
    )
    output_plugin: Optional[str] = Field(
        default=None, description="Output plugin for the Punchline"
    )
    input_plugin_port: Optional[int] = Field(
        default=None, description="Input plugin port for the Punchline"
    )
    output_plugin_hosts: Optional[str] = Field(
        default=None, description="Output plugin hosts for the Punchline"
    )

    def __str__(self) -> str:
        """
        Provide a string representation of the advanced Punchline workload attributes.
        """
        return (
            f"Pipeline Workers: {self.pipeline_workers}\n"
            f"Pipeline Batch Size: {self.pipeline_batch_size}\n"
            f"Pipeline Batch Delay: {self.pipeline_batch_delay}\n"
            f"Heap Size: {self.heap_size}\n"
            f"Log Level: {self.log_level}\n"
            f"Input Plugin: {self.input_plugin}\n"
            f"Output Plugin: {self.output_plugin}\n"
            f"Input Plugin Port: {self.input_plugin_port}\n"
            f"Output Plugin Hosts: {self.output_plugin_hosts}\n"
        )

    @classmethod
    def from_workload_context(
        cls,
        workload_context: WorkloadContext,
        langfuse_handler: Optional[CallbackHandler] = None,
    ) -> "PunchlineAdvanced":
        """
        Extract advanced information about a OpenSearch workload based on its context (YAML
        definitions).

        Args:
            workload_context (WorkloadContext): The workload context.
            langfuse_handler (Optional[CallbackHandler]): The LangFuse callback handler
        """
        prompt = PromptTemplate(
            template=(
                "You are an expert in Kubernetes.\n\n"
                "Based on the following Punchline definitions:\n\n"
                "{workload_context}\n\n"
                "Please provide advanced information about the following Punchline attributes:\n"
                "- Pipeline Workers\n"
                "- Pipeline Batch Size\n"
                "- Pipeline Batch Delay\n"
                "- Heap Size\n"
                "- Log Level\n"
                "- Input Plugin\n"
                "- Output Plugin\n"
                "- Input Plugin Port\n"
                "- Output Plugin Hosts\n\n"
                "Provide the information in a structured JSON format with the keys:\n"
                "'pipeline_workers', 'pipeline_batch_size', 'pipeline_batch_delay', 'heap_size', "
                "'log_level', 'input_plugin', 'output_plugin', 'input_plugin_port', "
                "'output_plugin_hosts'"
            ),
            input_variables=["workload_context"],
        )

        structured_model = get_structured_chain_for_service("kubernetes", PunchlineAdvanced)
        chain = prompt | structured_model
        invocation_args = {"workload_context": workload_context}

        if langfuse_handler is not None:
            return chain.invoke(
                invocation_args,
                config={"callbacks": [langfuse_handler]},
            )

        return chain.invoke(invocation_args)
