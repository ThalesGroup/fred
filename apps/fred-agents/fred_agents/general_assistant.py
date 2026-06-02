# Copyright Thales 2026
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
General-purpose assistant ReAct agent — the default Fred agent.

Why this module exists:
- provides the blank-slate agent that operators configure freely at enrollment
  time: they see every MCP server available in the pod catalog and select the
  ones they need
- replaces the former split between `simple_assistant` (no MCP) and the old
  `general_assistant` (all KF MCP servers by default), which was confusing

Key design:
- declares ALL enabled catalog servers in `default_mcp_servers` so the Tools
  tab in the enrollment form shows every available tool
- all servers are active by default (selected_mcp_server_ids = null); the
  operator unchecks the ones they do not need
- one `prompts.system` field lets operators specialise the role without creating
  a new agent template
- system prompt handles both the tool-equipped and no-tool cases

How to use it:
- import `GENERAL_ASSISTANT_AGENT` and register it first in the pod registry
  so that `fred-agents-cli` selects it as the default agent on connect
- operators create a named instance and deselect tools they don't need

Example:
- `from fred_agents.general_assistant import GENERAL_ASSISTANT_AGENT`
"""

from fred_sdk import (
    MCP_SERVER_KNOWLEDGE_FLOW_CORPUS,
    MCP_SERVER_KNOWLEDGE_FLOW_FS,
    MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS,
    MCP_SERVER_KNOWLEDGE_FLOW_PROMETHEUS_OPS,
    MCP_SERVER_KNOWLEDGE_FLOW_TABULAR,
    MCP_SERVER_KNOWLEDGE_FLOW_TEXT,
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ReActPolicy

_SYSTEM_PROMPT_EN = """\
You are a helpful, knowledgeable, and concise assistant.
Answer questions clearly and directly. When you are uncertain, say so.

If search or data tools are available, use them to ground your answers in real \
data before responding.
If no tools are available, answer from your training knowledge and say so clearly \
— do not pretend to have access to a document corpus or live data you cannot reach.
"""

_SYSTEM_PROMPT_FR = """\
Tu es un assistant serviable, compétent et concis.
Réponds aux questions clairement et directement. Lorsque tu n'es pas certain, dis-le.

Si des outils de recherche ou d'analyse de données sont disponibles, utilise-les \
pour ancrer tes réponses dans des données réelles avant de répondre.
Si aucun outil n'est disponible, réponds à partir de tes connaissances d'entraînement \
et indique-le clairement — ne prétends pas avoir accès à un corpus documentaire ou \
à des données en temps réel que tu ne peux pas atteindre.
"""

_SYSTEM_PROMPT = _SYSTEM_PROMPT_EN


class GeneralAssistantDefinition(ReActAgentDefinition):
    """
    General-purpose ReAct agent — the default Fred blank-slate agent.

    Why this class exists:
    - single entry point for operators who want to build a custom agent from
      scratch: they see every available MCP tool, pick what they need, and write
      their own system prompt
    - exposes all enabled catalog servers so the Tools tab is fully populated at
      enrollment time without requiring any code change

    Key design choices:
    - `default_mcp_servers` lists every enabled server in the pod catalog;
      `selected_mcp_server_ids = null` (default) means all are active, and the
      operator unchecks servers they don't want
    - system prompt handles both the fully-equipped and no-tool cases so the
      agent never claims unavailable capabilities
    - one `prompts.system` field lets operators specialise the role without
      forking a new template

    How to use it:
    - instantiate once and register it first in the pod registry (CLI default)
    - operators create a named instance and deselect unneeded tools

    Example:
    - `definition = GeneralAssistantDefinition()`
    """

    agent_id: str = "fred.github.assistant"
    role: str = "General-purpose assistant"
    description: str = (
        "Blank-slate assistant with access to all pod MCP tools. "
        "Select the tools you need at enrollment, write your own prompt, "
        "and build the agent that fits your use case."
    )
    description_by_lang: dict[str, str] | None = {
        "fr": (
            "Assistant généraliste avec accès à tous les outils MCP du pod. "
            "Sélectionnez les outils dont vous avez besoin à l'enrôlement, "
            "rédigez votre propre prompt et créez l'assistant adapté à votre cas d'usage."
        )
    }
    tags: tuple[str, ...] = ("general", "react")
    system_prompt_template: str = _SYSTEM_PROMPT

    # Core Knowledge Flow servers that are part of the standard platform deployment.
    # Demo servers and optional KF services (neo4j, statistics) are omitted here
    # because they are not guaranteed to be running — an unreachable declared server
    # crashes the agent turn. Operators who have those services running should create
    # a custom instance and add them via the control-plane agent form.
    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TEXT),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_CORPUS),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_FS),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TABULAR),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_PROMETHEUS_OPS),
        MCPServerRef(id="mcp-web-github-readonly"),
    )

    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System prompt",
            description=(
                "Instructions that define the assistant's role and focus. "
                "Leave blank to use the default general-purpose prompt."
            ),
            description_by_lang={
                "fr": (
                    "Instructions définissant le rôle et le périmètre de l'assistant. "
                    "Laissez vide pour utiliser le prompt généraliste par défaut."
                )
            },
            required=False,
            default=_SYSTEM_PROMPT_EN,
            default_by_lang={"fr": _SYSTEM_PROMPT_FR},
            ui=UIHints(group="Prompts", multiline=True, markdown=True, max_lines=12),
        ),
    )

    def policy(self) -> ReActPolicy:
        return ReActPolicy(system_prompt_template=self.system_prompt_template)


GENERAL_ASSISTANT_AGENT = GeneralAssistantDefinition()
