import logging

from fred_core import get_model
from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)

# ---------------------------
# Tuning spec (UI-editable)
# ---------------------------
BASIC_REACT_TUNING = AgentTuning(
    role="Define here the high-level role of the MCP agent.",
    description="Define here a detailed description of the MCP agent's purpose and behavior.",
    tags=[],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description=(
                "High-level instructions for the agent. "
                "State the mission, how to use the available tools, and constraints."
            ),
            required=True,
            default=(
                "You are an general assistant with tools. Use the available instructions and tools to solve the user's request.\n"
                "If you have tools:\n"
                "- ALWAYS use the tools at your disposal before providing any answer.\n"
                "- Prefer concrete evidence from tool outputs.\n"
                "- Be explicit about which tools you used and why.\n"
                "- When you reference tool results, keep short inline markers (e.g., [tool_name]).\n"
                "Current date: {today}."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
)


class BasicReActAgent(AgentFlow):
    """Simple ReAct agent used for dynamic UI-created agents."""

    tuning = BASIC_REACT_TUNING

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context=runtime_context)

        # Initialize MCP runtime
        self.mcp = MCPRuntime(
            agent=self,
        )
        await self.mcp.init()

    async def aclose(self):
        await self.mcp.aclose()

    def get_compiled_graph(self) -> CompiledStateGraph:
        agent = create_agent(
            model=get_default_chat_model(),
            system_prompt=self.render(self.get_tuned_text("prompts.system") or ""),
            tools=[*self.mcp.get_tools()],
            checkpointer=self.streaming_memory,
        )

        return agent
