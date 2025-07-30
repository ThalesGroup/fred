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
Module to represent advanced information about OpenSearch Dashboard workload.
"""

from typing import Optional, Literal

from langchain_core.prompts import PromptTemplate
from langfuse.callback import CallbackHandler
from pydantic import Field, BaseModel
from app.application_context import get_structured_chain_for_service

from app.features.frugal.structure.workload_context import WorkloadContext


class OpenSearchDashboardAdvanced(BaseModel):
    """
    Represents advanced informations about an OpenSearch Dashboard workload.
    """

    type: Literal["opensearch-dashboard"] = Field(
        default="opensearch-dashboard",
        description="The type of workload, used for discriminated union",
    )
    opensearch_hosts: list = Field(
        default_factory=list, description="List of OpenSearch backend hosts"
    )
    opensearch_ssl_verification_mode: str = Field(
        default="full", description="SSL verification mode for OpenSearch connection"
    )
    opensearch_username: Optional[str] = Field(
        default=None, description="Username for OpenSearch authentication"
    )
    opensearch_password: Optional[str] = Field(
        default=None, description="Password for OpenSearch authentication"
    )
    opensearch_request_timeout: int = Field(
        default=30000, description="Timeout for OpenSearch requests (in milliseconds)"
    )
    opensearch_shard_timeout: int = Field(
        default=0, description="Timeout for OpenSearch shards (in milliseconds)"
    )
    server_host: str = Field(
        default="0.0.0.0", description="Host to which the server binds"
    )
    server_port: int = Field(default=5601, description="Port to which the server binds")
    server_base_path: Optional[str] = Field(
        default=None, description="Base path that the server uses"
    )
    server_rewrite_base_path: bool = Field(
        default=False, description="Whether to rewrite the base path in requests"
    )
    server_ssl_enabled: bool = Field(
        default=False, description="Whether SSL is enabled on the server"
    )
    server_ssl_certificate: Optional[str] = Field(
        default=None, description="Path to the SSL certificate"
    )
    server_ssl_key: Optional[str] = Field(
        default=None, description="Path to the SSL key"
    )
    logging_dest: str = Field(
        default="stdout", description="Destination for logging output"
    )
    logging_level: str = Field(default="info", description="Logging level")

    def __str__(self) -> str:
        """
        Provide a string representation of the advanced OpenSearch Dashboard workload attributes.
        """
        return (
            f"OpenSearch Host: {self.opensearch_hosts}\n"
            f"OpenSearch SSL Verification Mode: {self.opensearch_ssl_verification_mode}\n"
            f"OpenSearch Username: {self.opensearch_username}\n"
            f"OpenSearch Password: {self.opensearch_password}\n"
            f"OpenSearch Request Timeout: {self.opensearch_request_timeout}\n"
            f"OpenSearch Shard Timeout: {self.opensearch_shard_timeout}\n"
            f"Server Host: {self.server_host}\n"
            f"Server Port: {self.server_port}\n"
            f"Server Base Path: {self.server_base_path}\n"
            f"Server Rewrite Base Path: {self.server_rewrite_base_path}\n"
            f"Server SSL Enabled: {self.server_ssl_enabled}\n"
            f"Server SSL Certificate: {self.server_ssl_certificate}\n"
            f"Server SSL Key: {self.server_ssl_key}\n"
            f"Logging Destination: {self.logging_dest}\n"
            f"Logging Level: {self.logging_level}\n"
        )

    @classmethod
    def from_workload_context(
        cls,
        workload_context: WorkloadContext,
        langfuse_handler: Optional[CallbackHandler] = None,
    ) -> "OpenSearchDashboardAdvanced":
        """
        Extract advanced information about a OpenSearch Dashboard workload based on its context
        (YAML definitions).

        Args:
            workload_context (WorkloadContext): The workload context.
            langfuse_handler (Optional[CallbackHandler]): The LangFuse callback handler
        """
        prompt = PromptTemplate(
            template=(
                "You are an expert in Kubernetes.\n\n"
                "Based on the following OpenSearch Dashboard definitions:\n\n"
                "{workload_context}\n\n"
                "Please provide advanced information about the following OpenSearch Dashboard "
                "attributes:\n"
                "- Opensearch Hosts\n"
                "- Opensearch SSL Verification Mode\n"
                "- Opensearch Username\n"
                "- Opensearch Password\n"
                "- Opensearch Request Timeout\n"
                "- Opensearch Shard Timeout\n"
                "- Server Host\n"
                "- Server Port\n"
                "- Server Base Path\n"
                "- Server Rewrite Base Path\n"
                "- Server SSL Enabled\n"
                "- Server SSL Certificate\n"
                "- Server SSL Key\n"
                "- Logging Destination\n"
                "- Logging Level\n\n"
                "Provide the information in a structured JSON format with the keys:\n"
                "'open_search_hosts', 'opensearch_ssl_verification_mode', 'opensearch_username', "
                "'opensearch_password', 'opensearch_request_timeout', 'opensearch_shard_timeout', "
                "'server_host', 'server_port', 'server_base_path', 'server_rewrite_base_path', "
                "'server_ssl_enabled', 'server_ssl_certificate', 'server_ssl_key', "
                "'logging_dest', 'logging_level'"
            ),
            input_variables=["workload_context"],
        )

        structured_model = get_structured_chain_for_service(
            "kubernetes", OpenSearchDashboardAdvanced
        )
        chain = prompt | structured_model
        invocation_args = {"workload_context": workload_context}

        if langfuse_handler is not None:
            return chain.invoke(
                invocation_args,
                config={"callbacks": [langfuse_handler]},
            )

        return chain.invoke(invocation_args)
