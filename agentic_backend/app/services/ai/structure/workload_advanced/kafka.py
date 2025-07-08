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
Module to represent advanced information about a Kafka workload.
"""

from typing import Optional, Literal

from langchain_core.prompts import PromptTemplate
from langfuse.callback import CallbackHandler
from pydantic import Field, BaseModel

from app.application_context import get_structured_chain_for_service
from app.services.ai.structure.workload_context import WorkloadContext


class KafkaAdvanced(BaseModel):
    """
    Represents advanced informations about a Kafka workload.
    """
    type: Literal["kafka"] = Field(
        default="kafka", description="The type of workload, used for discriminated union")
    broker_id: str = Field(
        default="None",
        description="The ID of the Kafka broker",
    )
    log_retention_ms: str = Field(
        default="None",
        description=(
            "How long Kafka will retain a log before it is eligible for "
            "deletion (in milliseconds)"
        ),
    )
    log_retention_bytes: str = Field(
        default="None",
        description=(
            "The maximum size of the log for a topic partition before Kafka "
            "deletes old segments to free up space"
        ),
    )
    log_segment_bytes: str = Field(
        default="None",
        description="Controls the size of each segment file within a partition",
    )
    replication_factor: str = Field(
        default="None",
        description="The number of copies of data Kafka maintains across brokers",
    )
    min_insync_replicas: str = Field(
        default="None",
        description=(
            "The minimum number of replicas that must acknowledge a write before "
            "it is considered successful"
        ),
    )
    message_max_bytes: str = Field(
        default="None",
        description="Defines the maximum size of a message that the broker will accept",
    )
    replica_fetch_max_bytes: str = Field(
        default="None",
        description=(
            "Should be set to at least the same value as message.max.bytes to "
            "ensure that replicas can fetch large messages"
        ),
    )
    broker_heap_size: str = Field(
        default="None",
        description=(
            "JVM heap size based on the broker’s workload (e.g., '4GB', '8GB')"
        ),
    )
    num_network_threads: str = Field(
        default="None",
        description="The number of network threads based on your network traffic",
    )
    socket_send_buffer_bytes: str = Field(
        default="None",
        description="Size of the send buffer for the socket",
    )
    socket_receive_buffer_bytes: str = Field(
        default="None",
        description="Size of the receive buffer for the socket",
    )
    log_cleanup_policy: str = Field(
        default="None",
        description=(
            "Determines how log segments are deleted: 'delete' for time-based or "
            "size-based retention, 'compact' for log compaction based on keys"
        ),
    )
    num_partitions: str = Field(
        default="None",
        description=(
            "The number of partitions based on the expected throughput and "
            "consumer group size"
        ),
    )
    topic_replication_factor: str = Field(
        default="None",
        description="Set the replication factor to ensure data redundancy",
    )
    topic_min_insync_replicas: str = Field(
        default="None",
        description=(
            "Ensure this is set in tandem with the producer's acks=all setting to "
            "guarantee that writes are only acknowledged when enough replicas are in sync"
        ),
    )

    def __str__(self) -> str:
        """
        Provide a string representation of the advanced Kafka workload attributes.
        """
        return (
            f"Broker ID: {self.broker_id}\n"
            f"Log Retention (ms): {self.log_retention_ms}\n"
            f"Log Retention (bytes): {self.log_retention_bytes}\n"
            f"Log Segment (bytes): {self.log_segment_bytes}\n"
            f"Replication Factor: {self.replication_factor}\n"
            f"Min In-Sync Replicas: {self.min_insync_replicas}\n"
            f"Message Max Bytes: {self.message_max_bytes}\n"
            f"Replica Fetch Max Bytes: {self.replica_fetch_max_bytes}\n"
            f"Broker Heap Size: {self.broker_heap_size}\n"
            f"Number of Network Threads: {self.num_network_threads}\n"
            f"Socket Send Buffer (bytes): {self.socket_send_buffer_bytes}\n"
            f"Socket Receive Buffer (bytes): {self.socket_receive_buffer_bytes}\n"
            f"Log Cleanup Policy: {self.log_cleanup_policy}\n"
            f"Number of Partitions: {self.num_partitions}\n"
            f"Topic Replication Factor: {self.topic_replication_factor}\n"
            f"Topic Min In-Sync Replicas: {self.topic_min_insync_replicas}"
        )

    @classmethod
    def from_workload_context(
        cls,
        workload_context: WorkloadContext,
        langfuse_handler: Optional[CallbackHandler] = None,
    ) -> "KafkaAdvanced":
        """
        Extract advanced information about a Kafka workload based on its context (YAML definitions).

        Args:
            workload_context (WorkloadContext): The workload context.
            langfuse_handler (Optional[CallbackHandler]): The LangFuse callback handler
        """
        prompt = PromptTemplate(
            template=(
                "You are an expert in Kubernetes.\n\n"
                "Based on the following Kafka definitions:\n\n"
                "{workload_context}\n\n"
                "Please provide advanced information about the following Kafka attributes:\n"
                "- Broker ID\n"
                "- Log Retention (ms)\n"
                "- Log Retention (bytes)\n"
                "- Log Segment (bytes)\n"
                "- Replication Factor\n"
                "- Min In-Sync Replicas\n"
                "- Message Max Bytes\n"
                "- Replica Fetch Max Bytes\n"
                "- Broker Heap Size\n"
                "- Number of Network Threads\n"
                "- Socket Send Buffer (bytes)\n"
                "- Socket Receive Buffer (bytes)\n"
                "- Log Cleanup Policy\n"
                "- Number of Partitions\n"
                "- Topic Replication Factor\n"
                "- Topic Min In-Sync Replicas\n\n"
                "Provide the information in a structured JSON format with the keys:\n"
                "'broker_id', 'log_retention_ms', 'log_retention_bytes', 'log_segment_bytes', "
                "'replication_factor', 'min_insync_replicas', 'message_max_bytes', "
                "'replica_fetch_max_bytes', 'broker_heap_size', 'num_network_threads', "
                "'socket_send_buffer_bytes', 'socket_receive_buffer_bytes', 'log_cleanup_policy', "
                "'num_partitions', 'topic_replication_factor', 'topic_min_insync_replicas'"
            ),
            input_variables=["workload_context"],
        )

        structured_model = get_structured_chain_for_service("kubernetes", KafkaAdvanced)
        chain = prompt | structured_model
        invocation_args = {"workload_context": workload_context}

        if langfuse_handler is not None:
            return chain.invoke(
                invocation_args,
                config={"callbacks": [langfuse_handler]},
            )

        return chain.invoke(invocation_args)
