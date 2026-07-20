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
General-purpose deep-agent assistant — first concrete `DeepAgentDefinition`.

Why this module exists:
- `DeepAgentRuntime` (fred-runtime) has existed since March/May but nothing
  registered a `DeepAgentDefinition` subclass anywhere, so it never ran in
  any shipped pod — this is the first one, deliberately the Deep-family
  counterpart of `GeneralAssistantDefinition` rather than a task-specific
  agent, so operators get a blank-slate planning assistant the same way they
  already get a blank-slate ReAct one
- kept intentionally minimal, matching `DeepAgentRuntime`'s own scope: no
  tool approval, no per-turn tool-call limit (both raise `NotImplementedError`
  at runtime if set), and no filesystem tools by default

Filesystem is deliberately excluded from `default_mcp_servers`:
- `deepagents.create_deep_agent` always registers `ls`/`read_file`/
  `write_file`/`edit_file`/`glob`/`grep` tools (its `FilesystemMiddleware` is
  mandatory), but `DeepAgentRuntime._build_deepagent_runtime_middleware`
  already guards every one of those names with a `run_limit=0`
  `ToolCallLimitMiddleware` whenever Fred's own filesystem MCP tools are not
  bound — so leaving `MCP_SERVER_KNOWLEDGE_FLOW_FS` out here means this agent
  gets no real or virtual file I/O, by construction, until an operator adds
  it explicitly. The `/fs` boundary is not yet hardened with a signed agent
  identity (`AGENT-FILESYSTEM-HARDENING-RFC.md`, FILES-01..06), so this stays
  out of the default footprint for the first exposed Deep agent.

How to use it:
- import `DEEP_ASSISTANT_AGENT` and register it in the pod registry

Example:
- `from fred_agents.deep_assistant import DEEP_ASSISTANT_AGENT`
"""

from fred_sdk import (
    MCP_SERVER_KNOWLEDGE_FLOW_CORPUS,
    MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS,
    MCP_SERVER_KNOWLEDGE_FLOW_PROMETHEUS_OPS,
    MCP_SERVER_KNOWLEDGE_FLOW_TABULAR,
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from fred_sdk.contracts.models import DeepAgentDefinition, ReActPolicy

_SYSTEM_PROMPT_EN = """\
You are a helpful, knowledgeable assistant that plans before it acts.
For questions with several steps, sketch a short plan first, then work \
through it — checking your own intermediate results before giving a final \
answer. For simple questions, just answer directly.

If search or data tools are available, use them to ground your answers in \
real data. If no tools are available, answer from your training knowledge \
and say so clearly — do not pretend to have access to a document corpus or \
live data you cannot reach.

You do not have file read/write tools in this configuration — do not claim \
to save, read, or edit files.
"""

_SYSTEM_PROMPT_FR = """\
Tu es un assistant serviable et compétent qui planifie avant d'agir.
Pour les questions à plusieurs étapes, esquisse d'abord un plan court, puis \
déroule-le — en vérifiant tes résultats intermédiaires avant de donner une \
réponse finale. Pour les questions simples, réponds directement.

Si des outils de recherche ou d'analyse de données sont disponibles, \
utilise-les pour ancrer tes réponses dans des données réelles. Si aucun \
outil n'est disponible, réponds à partir de tes connaissances d'entraînement \
et indique-le clairement.

Tu n'as pas d'outils de lecture/écriture de fichiers dans cette \
configuration — ne prétends pas enregistrer, lire ou modifier de fichiers.
"""


class DeepAssistantDefinition(DeepAgentDefinition):
    """
    General-purpose deep-agent assistant — the Deep-family counterpart of
    `GeneralAssistantDefinition`.

    Key design choices:
    - blank-slate: operators pick tools and write their own prompt, same
      enrollment pattern as the ReAct general assistant
    - no filesystem MCP server in `default_mcp_servers` (see module
      docstring); operators who want it can still add it explicitly via the
      control-plane agent form once they've made that call deliberately
    - one `prompts.system` field, same as every other blank-slate template

    Example:
    - `definition = DeepAssistantDefinition()`
    """

    agent_id: str = "fred.github.deep_assistant"
    role: str = "General-purpose deep assistant"
    description: str = (
        "Blank-slate planning assistant (LangGraph deep-agent runtime). "
        "Plans multi-step tasks before executing them. Select the tools you "
        "need at enrollment, write your own prompt."
    )
    description_by_lang: dict[str, str] | None = {
        "fr": (
            "Assistant généraliste planificateur (moteur deep-agent LangGraph). "
            "Planifie les tâches à plusieurs étapes avant de les exécuter. "
            "Sélectionnez les outils dont vous avez besoin à l'enrôlement, "
            "rédigez votre propre prompt."
        )
    }
    tags: tuple[str, ...] = ("general", "deep")
    system_prompt_template: str = _SYSTEM_PROMPT_EN

    # Same read/query-oriented defaults as GENERAL_ASSISTANT_AGENT, minus
    # MCP_SERVER_KNOWLEDGE_FLOW_FS — see module docstring.
    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id="document_access"),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_CORPUS),
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
                "Leave blank to use the default planning-assistant prompt."
            ),
            description_by_lang={
                "fr": (
                    "Instructions définissant le rôle et le périmètre de l'assistant. "
                    "Laissez vide pour utiliser le prompt planificateur par défaut."
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


DEEP_ASSISTANT_AGENT = DeepAssistantDefinition()
