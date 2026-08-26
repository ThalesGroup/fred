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
  time: they see every capability available in the pod catalog and select the
  ones they need
- replaces the former split between `simple_assistant` (no tools) and the old
  `general_assistant` (all KF MCP servers by default), which was confusing

Key design:
- declares a slim, end-user default set in `default_mcp_servers` (document
  search + tabular analysis, #2429); admin/ops servers are added per instance
  via the control-plane agent form, never by default
- all defaults are active by default (selected_capability_ids = null → the
  template's default capabilities, #1978, #1988); each is a capability the
  operator unchecks in the Tools tab when not needed
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
    MCP_SERVER_KNOWLEDGE_FLOW_TABULAR,
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ReActPolicy

from fred_agents.tool_pacing import REASONING_SAFE_TOOL_SELECTION

_BASE_SYSTEM_PROMPT_EN = """\
You are a helpful, knowledgeable, and concise assistant.
Answer questions clearly and directly. When you are uncertain, say so.

If search or data tools are available, use them to ground your answers in real \
data before responding.
If no tools are available, answer from your training knowledge and say so clearly \
— do not pretend to have access to a document corpus or live data you cannot reach.
"""

_BASE_SYSTEM_PROMPT_FR = """\
Tu es un assistant serviable, compétent et concis.
Réponds aux questions clairement et directement. Lorsque tu n'es pas certain, dis-le.

Si des outils de recherche ou d'analyse de données sont disponibles, utilise-les \
pour ancrer tes réponses dans des données réelles avant de répondre.
Si aucun outil n'est disponible, réponds à partir de tes connaissances d'entraînement \
et indique-le clairement — ne prétends pas avoir accès à un corpus documentaire ou \
à des données en temps réel que tu ne peux pas atteindre.
"""

# The shared global base prompt (e.g. the Mermaid output contract) is no longer
# baked into the editable prompt here. It is injected at execution time by the
# runtime (build_global_base_prompt_suffix) so it stays out of the operator-facing
# agent editor and applies even when the operator overrides this prompt.
_SYSTEM_PROMPT_EN = _BASE_SYSTEM_PROMPT_EN
_SYSTEM_PROMPT_FR = _BASE_SYSTEM_PROMPT_FR
_SYSTEM_PROMPT = _SYSTEM_PROMPT_EN


class GeneralAssistantDefinition(ReActAgentDefinition):
    """
    General-purpose ReAct agent — the default Fred blank-slate agent.

    Why this class exists:
    - single entry point for operators who want to build a custom agent from
      scratch: they pick the capabilities they need and write their own
      system prompt
    - ships end-user defaults only (document search + tabular, #2429); the
      Tools tab lets operators add or remove capabilities per instance

    Key design choices:
    - `default_mcp_servers` lists this template's default capabilities, MCP-backed
      and native alike; `selected_capability_ids = null` (default) activates
      them (each keyed by its capability id, #1988), and the operator unchecks
      the ones they don't want
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
    role: str = "Custom assistant"
    description: str = (
        "Build your own assistant: choose the tools it can use, like document "
        "search or data analysis, and describe its role in your own words. "
        "The best starting point for most use cases."
    )
    description_by_lang: dict[str, str] | None = {
        "fr": (
            "Créez votre propre assistant : choisissez les outils qu'il peut "
            "utiliser, comme la recherche documentaire ou l'analyse de "
            "données, et décrivez son rôle avec vos propres mots. Le meilleur "
            "point de départ pour la plupart des cas d'usage."
        )
    }
    tags: tuple[str, ...] = ("general", "react")
    system_prompt_template: str = _SYSTEM_PROMPT

    # End-user capabilities only (#2429): document search and tabular analysis.
    # Admin/ops servers (corpus administration, OpenSearch and Prometheus
    # monitoring, GitHub read-only) are too technical for the production
    # deployments this blank-slate template lands on, and each default also
    # feeds the #2408 dependency gate - enabling this agent for a team requires
    # every listed server to be usable by that team. Operators who need one of
    # the removed servers add it per instance via the control-plane agent form.
    #
    # Document search: `document_access` (native, #1906 pilot) rather than the
    # legacy inprocess `mcp-knowledge-flow-mcp-text` - the forward path under
    # live A/B evaluation against `react_rag_mcp`, which stays on the legacy
    # capability on purpose as the comparison baseline. Do not select both on
    # one instance (duplicate vector-search tool, see
    # `document_access/capability.py`'s module docstring).
    #
    # Filesystem (`mcp-knowledge-flow-fs`) is deliberately excluded: the /fs
    # boundary is not agent/team-scoped yet (AGENT-FILESYSTEM-HARDENING-RFC F1,
    # #2334) - same stance as `deep_assistant`. Do not re-add until that lands.
    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id="document_access"),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TABULAR),
    )

    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System prompt",
            description=(
                "Instructions that define the assistant's role and focus. "
                "Leave blank to use the built-in default prompt."
            ),
            description_by_lang={
                "fr": (
                    "Instructions définissant le rôle et le périmètre de l'assistant. "
                    "Laissez vide pour utiliser le prompt par défaut."
                )
            },
            required=False,
            default=_SYSTEM_PROMPT_EN,
            default_by_lang={"fr": _SYSTEM_PROMPT_FR},
            ui=UIHints(group="Prompts", multiline=True, markdown=True, max_lines=12),
        ),
    )

    def policy(self) -> ReActPolicy:
        return ReActPolicy(
            system_prompt_template=self.system_prompt_template,
            # REASON-01 §9 precondition 1 — see fred_agents.tool_pacing.
            tool_selection=REASONING_SAFE_TOOL_SELECTION,
        )


GENERAL_ASSISTANT_AGENT = GeneralAssistantDefinition()
