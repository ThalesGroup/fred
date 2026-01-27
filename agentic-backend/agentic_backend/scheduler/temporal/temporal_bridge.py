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

import logging

from langchain_core.callbacks import BaseCallbackHandler
from temporalio import activity

from agentic_backend.scheduler.agent_contracts import ProgressEventV1

logger = logging.getLogger(__name__)


class TemporalHeartbeatCallback(BaseCallbackHandler):
    """
    Hooks into LangGraph execution.
    When a node starts, it sends a Heartbeat to Temporal.
    """

    def __init__(self, task_id: str):
        self.task_id = task_id

    def on_chain_start(self, serialized, inputs, **kwargs):
        """
        Called when a LangGraph node (or the whole graph) starts.
        kwargs['name'] typically holds the Node Name (e.g., 'gather', 'analyze').
        """
        node_name = kwargs.get("name")

        # Filter out the root graph name if necessary, usually we only want nodes
        if node_name and node_name != "LangGraph":
            logger.info(f"[{self.task_id}] Entering node: {node_name}")

            # Create our Contract Object
            event = ProgressEventV1(
                label=f"Executing phase: {node_name}", phase=node_name
            )

            # SENT TO TEMPORAL SERVER
            # The workflow can check this heartbeat to know "Phase: analyze"
            try:
                # Only heartbeat when inside an activity context; info() raises if not.
                activity.info()
                activity.heartbeat(event.model_dump(mode="json"))
            except RuntimeError as exc:
                # Can happen if callback runs off-loop; log and continue without failing the activity.
                logger.warning(
                    "Heartbeat skipped (no running loop?): task=%s node=%s err=%s",
                    self.task_id,
                    node_name,
                    exc,
                )

    def on_tool_start(self, serialized, input_str, **kwargs):
        """Called when a tool is invoked."""
        tool_name = kwargs.get("name")
        try:
            activity.info()
            activity.heartbeat(
                ProgressEventV1(
                    label=f"Using tool: {tool_name}", phase="tool_execution"
                ).model_dump(mode="json")
            )
        except RuntimeError as exc:
            logger.warning(
                "Heartbeat skipped (no running loop?): task=%s tool=%s err=%s",
                self.task_id,
                tool_name,
                exc,
            )
