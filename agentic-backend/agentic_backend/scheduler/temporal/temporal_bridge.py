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

import asyncio
import inspect
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

            self._safe_heartbeat(
                event.model_dump(mode="json"),
                label=f"node:{node_name}",
            )

    def on_tool_start(self, serialized, input_str, **kwargs):
        """Called when a tool is invoked."""
        tool_name = kwargs.get("name")
        self._safe_heartbeat(
            ProgressEventV1(
                label=f"Using tool: {tool_name}", phase="tool_execution"
            ).model_dump(mode="json"),
            label=f"tool:{tool_name}",
        )

    # --- helpers ---
    def _safe_heartbeat(self, payload: dict, *, label: str) -> None:
        """
        Send a heartbeat if we're inside a Temporal activity context.
        - Handles the case where activity.heartbeat returns a coroutine (no running loop).
        - Suppresses warnings when not in an activity (e.g., local tests).
        """
        try:
            activity.info()
            hb = activity.heartbeat(payload)
            if inspect.isawaitable(hb):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(hb)
                except RuntimeError:
                    # No running loop (e.g., sync worker thread); drop quietly to avoid warnings.
                    return
        except RuntimeError as exc:
            logger.warning(
                "Heartbeat skipped (no activity context): task=%s label=%s err=%s",
                self.task_id,
                label,
                exc,
            )
