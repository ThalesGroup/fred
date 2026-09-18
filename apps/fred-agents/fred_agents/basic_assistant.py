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
Lightly equipped ReAct assistant — a conversation partner that reads what you
attach to it.

Why this module exists:
- the blank slate (`general_assistant`) deliberately ships nothing, and the
  knowledge assistant ships four packs; between them sat the most common ask —
  "an assistant I can drop a file into" — with no template to serve it
- keeping it separate is what lets the blank slate stay blank: every default a
  template carries becomes a hurdle a team must clear before an admin can
  enable it, which is the one thing the universal starting point must not have

Key design:
- one pack only (conversation attachments) plus reasoning, on from the first
  message; anything else is a capability the operator adds deliberately
- the prompt is short on purpose: with two tools bound there is no routing
  problem to solve, only a posture to set

How to use it:
- import `BASIC_ASSISTANT_AGENT` and register it in the pod registry

Example:
- `from fred_agents.basic_assistant import BASIC_ASSISTANT_AGENT`
"""

from fred_sdk import (
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ReActPolicy

from fred_agents.tool_pacing import REASONING_SAFE_TOOL_SELECTION

_SYSTEM_PROMPT_EN = """\
You are a helpful, knowledgeable and concise assistant.

Respond in {response_language}.

When the user attaches files to the conversation, treat them as the primary \
source: read them before answering, and make clear which one an answer comes \
from. Unless the user asks for a summary, an overview or the gist, cover the \
whole of what they attached rather than only its most relevant passages.

Be as brief as the content allows — covering everything is about what you \
leave out, not about length.

When you are uncertain, say so. Never claim access to a document corpus or to \
live data you have no tool to reach.
"""

_SYSTEM_PROMPT_FR = """\
Tu es un assistant serviable, compétent et concis.

Réponds en {response_language}.

Lorsque l'utilisateur joint des fichiers à la conversation, traite-les comme la \
source principale : lis-les avant de répondre et indique clairement de quel \
fichier vient une réponse. Sauf si l'utilisateur demande un résumé, un aperçu \
ou l'essentiel, couvre l'intégralité de ce qu'il a joint plutôt que ses seuls \
passages les plus pertinents.

Sois aussi bref que le contenu le permet — l'exhaustivité porte sur ce que tu \
omets, pas sur la longueur.

Lorsque tu n'es pas certain, dis-le. Ne prétends jamais avoir accès à un corpus \
documentaire ou à des données en temps réel qu'aucun outil ne te permet \
d'atteindre.
"""


class BasicAssistantDefinition(ReActAgentDefinition):
    """
    Conversational ReAct assistant pre-equipped to read attached files.

    Why this class exists:
    - the median first use of Fred is "here is a file, tell me about it"; that
      should not require knowing which capabilities implement it
    - it is the middle rung between the blank slate and the knowledge
      assistant, and exists as its own template precisely so neither has to
      compromise

    Key design choices:
    - `default_mcp_servers` carries ONE pack (conversation attachments), which
      is also the whole admission cost: a team needs those two capabilities
      usable before an admin can enable this template for it
    - `default_capabilities_config` puts `document_access` in attachments mode;
      without corpus search bound, widening its scope would bind a search this
      template cannot serve
    - `document_summarize` keeps its own confirmation default: nothing here
      justifies bypassing a gate the capability sets for itself

    How to use it:
    - instantiate once and register it in the pod registry after the blank
      slate, which stays the default agent

    Example:
    - `definition = BasicAssistantDefinition()`
    """

    agent_id: str = "fred.github.basic-assistant"
    role: str = "Basic assistant"
    role_by_lang: dict[str, str] | None = {"fr": "Assistant basique"}
    description: str = (
        "A ready-to-use assistant for everyday questions. Attach files to the "
        "conversation and it reads them before answering. It thinks before it "
        "replies, and you can add more tools whenever you need them."
    )
    description_by_lang: dict[str, str] | None = {
        "fr": (
            "Un assistant prêt à l'emploi pour les questions du quotidien. "
            "Joignez des fichiers à la conversation et il les lit avant de "
            "répondre. Il réfléchit avant de répondre, et vous pouvez lui "
            "ajouter d'autres outils quand vous en avez besoin."
        )
    }
    tags: tuple[str, ...] = ("general", "react")
    system_prompt_template: str = _SYSTEM_PROMPT_EN

    # The "conversation attachments" pack, and only it: `document_access` in
    # attachments mode plus `document_summarize`. Exactly what ticking that
    # pack in the agent form selects, so the form reads the pack as on.
    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id="document_access"),
        MCPServerRef(id="document_summarize"),
    )

    default_capabilities_config: dict[str, dict[str, object]] = {
        "document_access": {
            "search_attachments_only": True,
            "show_attach_files_control": True,
        },
    }

    reasoning_enabled: bool = True
    reasoning_default_on: bool = True

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


BASIC_ASSISTANT_AGENT = BasicAssistantDefinition()
