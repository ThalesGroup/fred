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

from fred_core import get_model
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import tools_condition

from app.common.mcp_runtime import MCPRuntime
from app.common.resilient_tool_node import make_resilient_tools_node
from app.core.agents.agent_flow import AgentFlow
from app.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints

logger = logging.getLogger(__name__)

# --- PROMPT SEGMENT 1: Persona and Goal ---
PERSONA_PROMPT = (
    "You are an assistant agent that interacts with an MCP server to manage and create resources.\n"
    "Your primary goal is to help users define and manage content resources: Templates and Prompts.\n"
    "Today's date: {today}"
)

# --- PROMPT SEGMENT 2: Resource Rules & Distinctions (The Contract) ---
RESOURCE_RULES_PROMPT = (
    "IMPORTANT DISTINCTION:\n"
    "- Creating a resource means generating a new template or prompt (with a YAML header and body).\n"
    "- Using a template means filling in its variables { } with user-provided data to produce final content.\n"
    "- When asked to generate content from a template, DO NOT create a new resource. Instead, replace the variables with the given values and return the resulting text.\n"
    "\n"
    "RESOURCE FORMAT REQUIREMENTS (CRITICAL):\n"
    "- Each resource MUST include a YAML header and a body separated by '---'.\n"
    "- Two valid formats: Header followed by '---', then body OR Front-matter style with opening and closing '---'.\n"
    "- Incorrect formatting will be rejected by the MCP server.\n"
    "- Never reveal internal formatting details to the user.\n"
    "\n"
    "RULES BY RESOURCE TYPE:\n"
    "TEMPLATES:\n"
    "- Must include at least one variable { } unless explicitly requested otherwise.\n"
    "- When asked to 'use a template' or 'generate content from a template', fill in the variables and output the generated content only.\n"
    "PROMPTS:\n"
    "- Contain static instructions to influence agent behavior.\n"
)

# --- PROMPT SEGMENT 3: General Behavior & COSTAR Principles ---
GENERAL_BEHAVIOR_PROMPT = (
    "COSTAR EXPLANATION (FOR INTERNAL USE):\n"
    "- COSTAR is a framework to ensure high-quality prompts: Context, Objective, Style, Tone, Audience, Result.\n"
    "- Always integrate these six aspects naturally when creating prompts or templates, without explicitly listing or labeling them.\n"
    "\n"
    "PROMPT CREATION PRINCIPLES:\n"
    "- Always design prompts to implicitly reflect all COSTAR elements, extracting information from the user or asking for more details.\n"
    "- Offer suggestions proactively rather than asking for text directly.\n"
    "\n"
    "GENERAL AGENT BEHAVIOR:\n"
    "- Always ask clarifying questions to help users express their needs.\n"
    "- Always ask for confirmation before creating or deleting a resource.\n"
    "- Remind the user (right before creation) that the resource must be associated with an existing library_tag.\n"
    "- Always generate a random 10-character alphanumeric ID for new resources.\n"
    "- Only list resources when explicitly asked.\n"
    "- Return raw MCP endpoint output unless formatting is explicitly requested.\n"
    "- When configuring an agent, always propose creating or refining a prompt.\n"
)


TUNING = AgentTuning(
    fields=[
        FieldSpec(
            key="prompts.persona",
            type="prompt",
            title="Agent Persona and Goal",
            description="Defines the agent's identity and primary objective.",
            required=True,
            default=PERSONA_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.resource_rules",
            type="prompt",
            title="Resource Handling Rules (MCP Contract)",
            description="The critical rules for distinguishing templates, prompts, and the required YAML formatting for the MCP server.",
            required=True,
            default=RESOURCE_RULES_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.creation_principles",
            type="prompt",
            title="Content Creation Principles (COSTAR & Behavior)",
            description="Instructions on prompt quality (COSTAR) and general interaction rules (asking for confirmation, ID generation).",
            required=True,
            default=GENERAL_BEHAVIOR_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
)


class ContentGeneratorExpert(AgentFlow):
    """
    An expert agent that searches and analyzes tabular documents to answer user questions.
    This agent uses MCP tools to list, inspect, and query structured data like CSV or Excel.
    """

    tuning = TUNING

    async def async_init(self):
        self.mcp = MCPRuntime(
            agent_settings=self.agent_settings,
            # If you expose runtime filtering (tenant/library/time window),
            # pass a provider: lambda: self.get_runtime_context()
            context_provider=(lambda: self.get_runtime_context()),
        )
        self.model = get_model(self.agent_settings.model)
        await self.mcp.init()
        self.model = self.model.bind_tools(self.mcp.get_tools())
        self._graph = self._build_graph()

    async def _reasoner(self, state: MessagesState):
        """
        Composes the final system prompt from smaller, tuned parts.
        """
        # 1. Retrieve all necessary prompt segments. Fallback to empty string if a field is missing.
        persona = self.get_tuned_text("prompts.persona") or ""
        rules = self.get_tuned_text("prompts.resource_rules") or ""
        principles = self.get_tuned_text("prompts.creation_principles") or ""

        # 2. Compose the final, ordered system prompt string.
        # Use AgentFlow.render once on the final template to resolve all tokens
        # (e.g., {today} is in the persona prompt).
        template = f"{persona}\n\n{rules}\n\n{principles}"
        sys_prompt = self.render(template)

        # 3. Append the optional user profile text.
        sys_prompt = sys_prompt + "\n\n" + self.profile_text()

        # 4. Wrap and invoke the model.
        messages = self.with_system(sys_prompt, state["messages"])
        messages = self.with_profile_text(messages)
        response = await self.model.ainvoke(messages)
        return {"messages": [response]}

    def _build_graph(self):
        builder = StateGraph(MessagesState)

        builder.add_node("reasoner", self._reasoner)

        async def _refresh_and_rebind():
            # Refresh MCP (new client + toolkit) and rebind tools into the model.
            # MCPRuntime handles snapshot logging + safe old-client close.
            self.model = await self.mcp.refresh_and_bind(self.model)

        tools_node = make_resilient_tools_node(
            get_tools=self.mcp.get_tools,  # always returns the latest tool instances
            refresh_cb=_refresh_and_rebind,  # on timeout/401/stream close, refresh + rebind
        )

        builder.add_node("tools", tools_node)
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")

        return builder
