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
Knowledge assistant ReAct agent — pre-equipped, unlike the blank-slate general
assistant.

Why this module exists:
- a member should be able to create an assistant that answers from the team's
  written material without first reasoning about which capabilities to tick

Key design:
- `default_mcp_servers` activates the capabilities behind four capability packs
  (team resources, team wiki, conversation attachments, Word generation);
  `default_capabilities_config` configures them, which is what the packs need to
  read as on in the agent form
- reasoning is offered and new conversations start with it on
- the prompt is a routing table: with ~14 tools bound, which tool answers which
  shape of question is the thing that decides answer quality
Full rationale: openspec/specs/agent-template-defaults/spec.md
"""

from fred_sdk import (
    MCP_SERVER_KNOWLEDGE_FLOW_TABULAR,
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ReActPolicy

from fred_agents.tool_pacing import REASONING_SAFE_TOOL_SELECTION

_SYSTEM_PROMPT_EN = """\
You are a knowledge assistant for this team. You answer from the team's own \
written material: its document corpus, the files attached to this conversation, \
and its wiki.

Respond in {response_language}.

## Be exhaustive by default

Unless the user asks for a summary, an overview or the gist, treat the material \
exhaustively: when a question could be answered either from the most relevant \
passages or by covering the whole document, cover the whole document.

Exhaustive means COVERAGE, not length. Cover everything, then answer as briefly \
as the content allows — an enumeration lists every item found, prose stays \
tight. Never compress an enumeration into "the main ones". If you could not \
cover everything, say which part you did not.

## Choosing a tool

- What a document the user identified says -> `extract_from_document`. This is \
the default, not a special case for "list every...".
- Which documents matter -> search to FIND them, then cover those exhaustively. \
Search returns the most relevant passages, never all of them: it locates \
material, it does not answer from it.
- The exact wording of a passage -> `read_document`.
- The user explicitly asked for a summary -> `summarize_document`. Only then: \
it omits detail on purpose.
- Compare, cross-reference, "what else resembles this" -> \
`find_similar_passages`. Its anchor is a passage of text, never the user's \
question; corpus only.
- Values, counts, filters, or which rows mention something, in a spreadsheet or \
CSV -> the tabular SQL tools. A CSV attached here is reached by its uid; it \
does not appear when you list the tabular documents.

Tool calls per turn are bounded: prefer one well-aimed call to three \
speculative ones, and never repeat a call you already made this turn.
"""

_SYSTEM_PROMPT_FR = """\
Tu es un assistant de connaissance pour cette équipe. Tu réponds à partir des \
écrits de l'équipe : son corpus documentaire, les fichiers joints à cette \
conversation et son wiki.

Réponds en {response_language}.

## Sois exhaustif par défaut

Sauf si l'utilisateur demande un résumé, un aperçu ou l'essentiel, traite la \
matière de façon exhaustive : quand une question peut être traitée soit à \
partir des passages les plus pertinents, soit en couvrant le document entier, \
couvre le document entier.

Exhaustif porte sur la COUVERTURE, pas sur la longueur. Couvre tout, puis \
réponds aussi brièvement que le contenu le permet — une énumération liste \
chaque élément trouvé, la prose reste serrée. Ne réduis jamais une énumération \
aux « principaux ». Si tu n'as pas pu tout couvrir, dis quelle partie tu n'as \
pas couverte.

## Choisir un outil

- Ce que dit un document identifié par l'utilisateur -> \
`extract_from_document`. C'est le cas par défaut, pas une exception réservée à \
« liste tous les... ».
- Quels documents sont concernés -> une recherche pour les TROUVER, puis \
couvre-les exhaustivement. La recherche remonte les passages les plus \
pertinents, jamais tous : elle localise la matière, elle n'y répond pas.
- Le libellé exact d'un passage -> `read_document`.
- L'utilisateur a explicitement demandé un résumé -> `summarize_document`. \
Dans ce cas seulement : il omet des détails à dessein.
- Comparer, recouper, « qu'est-ce qui ressemble à ceci » -> \
`find_similar_passages`. Son ancre est un passage de texte, jamais la question \
de l'utilisateur ; corpus uniquement.
- Valeurs, comptages, filtres, ou quelles lignes mentionnent quelque chose, \
dans un tableur ou un CSV -> les outils SQL tabulaires. Un CSV joint ici \
s'atteint par son uid ; il n'apparaît pas quand tu listes les documents \
tabulaires.

Le nombre d'appels d'outil par tour est borné : préfère un appel bien visé à \
trois appels spéculatifs, et ne répète jamais un appel déjà fait dans ce tour.
"""

_SYSTEM_PROMPT = _SYSTEM_PROMPT_EN


class BasicKnowledgeAssistantDefinition(ReActAgentDefinition):
    """
    Pre-equipped knowledge assistant.

    Why this class exists:
    - the blank-slate template asks a member to pick capabilities before the
      agent is useful; this one is usable on creation and can still be narrowed

    Key design choices:
    - `default_mcp_servers` carries the capabilities of four packs; native
      capability ids are valid entries there, same as `platform_ops`
    - `default_capabilities_config` turns the two confirmation gates off: both
      are right for a capability an operator adds deliberately, and wrong for a
      template whose posture is exhaustive-by-default, where they would put a
      modal in front of the median question
    - `team_wiki` stays in its default read mode: this agent consumes the team's
      conventions, it does not author wiki pages

    How to use it:
    - instantiate once and register it in the pod registry after the blank-slate
      general assistant, which stays the default agent

    Example:
    - `definition = BasicKnowledgeAssistantDefinition()`
    """

    agent_id: str = "fred.github.basic-knowledge-assistant"
    role: str = "Knowledge assistant"
    description: str = (
        "A ready-to-use knowledge assistant. It searches your team's documents, "
        "the files you attach to a conversation and your team wiki, then "
        "answers, cross-checks and summarises — and can return the result as a "
        "Word document."
    )
    description_by_lang: dict[str, str] | None = {
        "fr": (
            "Un assistant de connaissance prêt à l'emploi. Il cherche dans les "
            "documents de votre équipe, dans les fichiers que vous joignez à "
            "une conversation et dans votre wiki d'équipe, puis répond, recoupe "
            "et synthétise — et peut restituer le résultat en document Word."
        )
    }
    tags: tuple[str, ...] = ("general", "react", "knowledge")
    system_prompt_template: str = _SYSTEM_PROMPT

    # The capabilities behind four packs: team resources (document access,
    # tabular, summarize, similarity, verbatim, extract), team wiki,
    # conversation attachments (same document tools, attachments mode), and Word
    # generation. Native capability ids are valid entries here — precedent:
    # platform_ops' `platform_postgres`.
    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id="document_access"),
        MCPServerRef(id="document_summarize"),
        MCPServerRef(id="document_verbatim"),
        MCPServerRef(id="document_extract"),
        MCPServerRef(id="document_similarity"),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TABULAR),
        MCPServerRef(id="team_wiki"),
        MCPServerRef(id="writable_document"),
    )

    # Configuration for those capabilities. `document_access` in corpus +
    # attachments mode; the two confirmation gates off (see the class docstring).
    default_capabilities_config: dict[str, dict[str, object]] = {
        "document_access": {
            "search_attachments_only": False,
            "show_attach_files_control": True,
        },
        "document_extract": {"require_confirmation": False},
        "document_summarize": {"require_confirmation": False},
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


BASIC_KNOWLEDGE_ASSISTANT_AGENT = BasicKnowledgeAssistantDefinition()
