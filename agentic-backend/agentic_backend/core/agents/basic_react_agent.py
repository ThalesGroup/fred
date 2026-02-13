import logging

from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.common.structures import AgentChatOptions
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

# Always append citation guidance, even if the agent has a custom system prompt.
_CITATION_POLICY = (
    "\n\n"
    "Citations for document search tools:\n"
    "- If a tool returns document search results (vector hits with title/content/rank), "
    "cite sources with bracketed numbers like [1], [2]. Use the hit rank when available; "
    "otherwise use list order.\n"
    "- If multiple sources support a statement, include multiple citations (e.g., [1][3])."
)

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
                "You are a general assistant with tools. Use the available instructions and tools to solve the user's request.\n"
                "If you have tools:\n"
                "- ALWAYS use the tools at your disposal before providing any answer.\n"
                "- Prefer concrete evidence from tool outputs.\n"
                "- Be explicit about which tools you used and why.\n"
                "- When you reference tool results, keep short inline markers (e.g., [tool_name]).\n"
                "- When a tool returns document search results (vector hits with title/content/rank), cite sources with\n"
                "  bracketed numbers like [1], [2]. Use the hit rank when available; otherwise use list order.\n"
                "- If multiple sources support a statement, include multiple citations (e.g., [1][3]).\n"
                "Current date: {today}."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="chat_options.attach_files",
            type="boolean",
            title="Allow file attachments",
            description="Show file upload/attachment controls for this agent.",
            required=False,
            default=False,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.libraries_selection",
            type="boolean",
            title="Document libraries picker",
            description="Let users select document libraries/knowledge sources for this agent.",
            required=False,
            default=False,
            ui=UIHints(group="Chat options"),
        ),
        # FieldSpec(
        #     key="chat_options.search_policy_selection",
        #     type="boolean",
        #     title="Search policy selector",
        #     description="Expose the search policy toggle (hybrid/semantic/strict).",
        #     required=False,
        #     default=False,
        #     ui=UIHints(group="Chat options"),
        # ),
        # FieldSpec(
        #     key="chat_options.search_rag_scoping",
        #     type="boolean",
        #     title="RAG scope selector",
        #     description="Expose the RAG scope control (documents-only vs hybrid vs knowledge).",
        #     required=False,
        #     default=False,
        #     ui=UIHints(group="Chat options"),
        # ),
        # FieldSpec(
        #     key="chat_options.deep_search_delegate",
        #     type="boolean",
        #     title="Deep search delegate toggle",
        #     description="Allow delegation to a senior agent for deep search.",
        #     required=False,
        #     default=False,
        #     ui=UIHints(group="Chat options"),
        # ),
    ],
)


@expose_runtime_source("agent.BasicReActAgent")
class BasicReActAgent(AgentFlow):
    """Simple ReAct agent used for dynamic UI-created agents."""

    tuning = BASIC_REACT_TUNING
    default_chat_options = AgentChatOptions(
        search_policy_selection=False,
        libraries_selection=False,
        search_rag_scoping=False,
        deep_search_delegate=False,
        attach_files=False,
    )

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context=runtime_context)

        # Initialize MCP runtime
        self.mcp = MCPRuntime(
            agent=self,
        )
        await self.mcp.init()

    async def aclose(self):
        await self.mcp.aclose()

    def get_compiled_graph(
        self, checkpointer: Checkpointer | None = None
    ) -> CompiledStateGraph:
        base_prompt = self.render(self.get_tuned_text("prompts.system") or "")
        return create_agent(
            model=get_default_chat_model(),
            system_prompt=f"{base_prompt}{_CITATION_POLICY}",
            tools=[*self.mcp.get_tools()],
            checkpointer=checkpointer,
        )
