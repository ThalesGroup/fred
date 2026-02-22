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

# Append citation guidance only when document-search tools are available.
_CITATION_POLICY = (
    "\n\n"
    "Citations for document search tools:\n"
    "- If a tool returns document search results (vector hits with title/content/rank), "
    "cite sources with bracketed numbers like [1], [2]. Use the hit rank when available; "
    "otherwise use list order.\n"
    "- If multiple sources support a statement, include multiple citations (e.g., [1][3])."
)

_NO_TOOLS_POLICY = (
    "\n\n"
    "Tool availability:\n"
    "- No external tool is available in this session.\n"
    "- Do NOT claim you searched the web, queried a database, or called any tool.\n"
    "- Do NOT write fake tool markers such as [web search], [tool], or similar.\n"
    "- Answer normally without repeating capability disclaimers.\n"
    "- Mention the limitation only when the user's request explicitly requires unavailable external lookup.\n"
    "- When needed, keep that limitation note short and only once in the answer."
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
                "If tools are available:\n"
                "- Use only the tools that are explicitly available in this session.\n"
                "- Prefer concrete evidence from tool outputs.\n"
                "- Be explicit about which tools you used and why.\n"
                "- Never claim any tool result that was not actually returned by a tool call.\n"
                "- When a tool returns document search results (vector hits with title/content/rank), cite sources with\n"
                "  bracketed numbers like [1], [2]. Use the hit rank when available; otherwise use list order.\n"
                "- If multiple sources support a statement, include multiple citations (e.g., [1][3]).\n"
                "If no tool is available:\n"
                "- Answer directly without proactive capability disclaimers.\n"
                "- Only mention missing external lookup capability when it is strictly necessary for the request.\n"
                "- Never mention fake tools such as [web search].\n"
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
        tools = [*self.mcp.get_tools()]
        tool_names = [tool.name for tool in tools]

        if tool_names:
            listed_tools = "\n".join(f"- {name}" for name in tool_names)
            tool_policy = (
                "\n\n"
                "Available tools (exact names):\n"
                f"{listed_tools}\n"
                "Rules:\n"
                "- You may only call tools listed above.\n"
                "- Never invent tool names.\n"
                "- Never present tool output unless a tool actually returned it."
            )
            system_prompt = f"{base_prompt}{tool_policy}{_CITATION_POLICY}"
        else:
            system_prompt = f"{base_prompt}{_NO_TOOLS_POLICY}"

        return create_agent(
            model=get_default_chat_model(),
            system_prompt=system_prompt,
            tools=tools,
            checkpointer=checkpointer,
        )
