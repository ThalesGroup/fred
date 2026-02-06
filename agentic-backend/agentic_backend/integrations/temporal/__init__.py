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
Get the Temporal tools and ToolNode to make your agent capable of submitting
and monitoring Temporal workflows.

The typical usage is for an interactive agent to start a long running agentic task
such as a deep research, a report generation, or a business process orchestration.

For LangGraph devs:
- Bind on the model side: `model = model.bind_tools(get_temporal_tools())`
- Add tool execution node: `builder.add_node("tools", get_temporal_tool_node())`
- Wire: reasoner -> tools (conditional), tools -> reasoner.

Minimal snippet:
```
tools = get_temporal_tools()  # temporal_submit(request_text, target_agent, project_id?)
model = model.bind_tools(tools)
tool_node = get_temporal_tool_node()

builder = StateGraph(MessagesState)
builder.add_node("reasoner", reasoner_fn)
builder.add_node("tools", tool_node)
builder.add_edge(START, "reasoner")
builder.add_conditional_edges("reasoner", tools_condition)
builder.add_edge("tools", "reasoner")
```
"""

from agentic_backend.integrations.temporal.tools import TemporalTools


def get_temporal_tools():
    """
    Return the list[BaseTool] for Temporal submit/status using the shared app context.
    Use when binding tools on the model (LangChain style).

    Code snippet:
    ```
    tools = get_temporal_tools()
    model = model.bind_tools(tools)
    ```
    """
    return TemporalTools.from_app_context().tools()


def get_temporal_tool_node():
    """
    Return a ToolNode wired with Temporal tools (LangGraph execution node).
    Use in the graph to execute tool calls emitted by the model.

    Code snippet:
    ```
    tool_node = get_temporal_tool_node()
    builder.add_node("tools", tool_node)
    ```
    """
    from langgraph.prebuilt import ToolNode

    return ToolNode(get_temporal_tools())
