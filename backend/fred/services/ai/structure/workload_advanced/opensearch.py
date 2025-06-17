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
Module to represent advanced information about OpenSearch workload.
"""

from typing import Optional, Literal
from fred.application_context import get_structured_chain_for_service

from langchain_core.prompts import PromptTemplate
from langfuse.callback import CallbackHandler
from pydantic import Field, BaseModel

from fred.services.ai.structure.workload_context import WorkloadContext


class OpenSearchAdvanced(BaseModel):
    """
    Represents advanced informations about a OpenSearch workload.
    """
    type: Literal["opensearch"] = Field(
        default="opensearch", description="The type of workload, used for discriminated union")
    shard_size_gb: Optional[str] = Field(
        default=None,
        description="Size of each shard, typically between 10 GB and 50 GB",
    )
    shard_count: Optional[str] = Field(
        default=None,
        description="Total number of shards, should be an even multiple of data node count",
    )
    shards_per_data_node: Optional[str] = Field(
        default=None,
        description="Recommended to aim for 25 shards or fewer per GiB of heap memory",
    )
    def __str__(self) -> str:
        """
        Provide a string representation of the advanced OpenSearch workload attributes.
        """
        return (
            f"Shard Size (GB): {self.shard_size_gb}\n"
            f"Shard Count: {self.shard_count}\n"
            f"Shards per Data Node: {self.shards_per_data_node}\n"
        )

    @classmethod
    def from_workload_context(
        cls,
        workload_context: WorkloadContext,
        langfuse_handler: Optional[CallbackHandler] = None,
    ) -> "OpenSearchAdvanced":
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
                "Based on the following OpenSearch definitions:\n\n"
                "{workload_context}\n\n"
                "Please provide advanced information about the following OpenSearch attributes:\n"
                "- Shard Size (GB)\n"
                "- Shard Count\n"
                "- Shards per Data Node\n"
                "Provide the information in a structured JSON format with the keys:\n"
                "'shard_size_gb', 'shard_count', 'shards_per_data_node'"
            ),
            input_variables=["workload_context"],
        )

        structured_model = get_structured_chain_for_service("kubernetes", OpenSearchAdvanced)
        chain = prompt | structured_model
        invocation_args = {"workload_context": workload_context}

        if langfuse_handler is not None:
            return chain.invoke(
                invocation_args,
                config={"callbacks": [langfuse_handler]},
            )

        return chain.invoke(invocation_args)
