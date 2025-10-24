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


import json
import logging
from typing import TYPE_CHECKING, Dict, List

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool  # Import necessary type
from langgraph.graph import MessagesState

if TYPE_CHECKING:
    # We only need the type hint for the tools list
    pass

logger = logging.getLogger(__name__)


class StandardToolNode:
    """
    A reusable LangGraph node that executes tools requested in the last AIMessage.
    This node is not needed if using LangGraph's built-in ToolNode, but is provided
    here as an example of how to build a custom tool execution node with enhanced
    resilience features.

    It relies on the tools list provided during initialization, which should
    already contain the necessary RefreshableTool wrappers for resilience.
    """

    def __init__(self, tools: List[BaseTool]):
        """Initializes the node with a list of available tools."""
        self.tools_by_name: Dict[str, BaseTool] = {tool.name: tool for tool in tools}

    async def __call__(self, state: MessagesState) -> Dict[str, List[ToolMessage]]:
        """
        Executes the tools requested in the last AIMessage.
        """
        last_message = state["messages"][-1]
        tool_results: List[ToolMessage] = []

        # Safely access optional 'tool_calls' attribute using getattr to avoid static type
        # checker errors when messages can be multiple concrete message classes.
        tool_calls = getattr(last_message, "tool_calls", None)
        if not tool_calls:
            logger.warning("ToolNode called without tool_calls in the last message.")
            return {"messages": []}

        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool = self.tools_by_name.get(tool_name)

            if not tool:
                error_msg = (
                    f"Tool '{tool_name}' requested but not found in available tools."
                )
                logger.error(error_msg)
                tool_results.append(
                    ToolMessage(
                        content=f"Error: {error_msg}",
                        tool_call_id=tool_call["id"],
                        name=tool_name,
                    )
                )
                continue

            try:
                # 💡 This calls the wrapped RefreshableTool's .ainvoke/.arun method.
                # All 401/refresh logic is hidden here!
                result = await tool.ainvoke(tool_call["args"])

                # LangGraph expects the output to be a string/json in ToolMessage
                content = json.dumps(result)

                tool_results.append(
                    ToolMessage(
                        content=content, tool_call_id=tool_call["id"], name=tool_name
                    )
                )
            except Exception as e:
                logger.exception(
                    f"Tool execution failed for {tool_name} (Resilience handled)."
                )
                # The RefreshableTool should ideally catch and retry, but if it
                # fails permanently, we return a clear error message.
                tool_results.append(
                    ToolMessage(
                        content=f"Tool Failed: {e.__class__.__name__}. See logs for details.",
                        tool_call_id=tool_call["id"],
                        name=tool_name,
                    )
                )

        return {"messages": tool_results}
