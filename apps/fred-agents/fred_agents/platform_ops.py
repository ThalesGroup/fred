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
Platform operations assistant ReAct agent — the admin-ops ready-made template.

Why this module exists:
- ships the ready-made template for the admin-ops capability family
  (`docs/swift/rfc/admin-ops-capabilities/PLATFORM-POSTGRES.md` §5, parent
  ADMIN-OPS-AGENTS-RFC §5): operators diagnose their Fred deployment by
  chatting instead of shelling into psql
- defaults to the `platform_postgres` capability (read-only SQL over the
  platform's own database); each later admin-ops capability WP appends itself
  to this template's default list

Key design:
- the template is itself an ADMIN_GATED capability, invisible to every team
  until granted — the admin team roster is the trust boundary, the capability
  itself is server-enforced read-only
- prompt lives in `prompts/basic_react_platform_ops_system_prompt.md` and is
  editable per instance through the `prompts.system` field
- no "cite which query produced each number" instruction — per-query
  attribution already lives in the session history's tool calls (spec §5)

How to use it:
- import `PLATFORM_OPS_AGENT` and add it to the pod registry
"""

from fred_sdk import (
    FieldSpec,
    GuardrailDefinition,
    MCPServerRef,
    UIHints,
    load_agent_prompt_markdown,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ReActPolicy

from fred_agents.tool_pacing import REASONING_SAFE_TOOL_SELECTION

_SYSTEM_PROMPT = load_agent_prompt_markdown(
    package="fred_agents.platform_ops",
    file_name="basic_react_platform_ops_system_prompt.md",
)


class PlatformOpsReActDefinition(ReActAgentDefinition):
    """
    Read-only platform-operations ReAct agent served by the standalone agents pod.
    """

    agent_id: str = "fred.github.platform_ops"
    role: str = "Platform operations assistant"
    description: str = (
        "A read-only operations assistant for this Fred deployment: it answers "
        "questions about teams, agents, sessions, and usage by querying the "
        "platform's own database. For admin teams — it can inspect everything "
        "and modify nothing."
    )
    description_by_lang: dict[str, str] | None = {
        "fr": (
            "Un assistant d'exploitation en lecture seule pour ce déploiement "
            "Fred : il répond aux questions sur les équipes, les agents, les "
            "sessions et l'usage en interrogeant la base de données de la "
            "plateforme. Réservé aux équipes d'administration — il peut tout "
            "inspecter et ne rien modifier."
        )
    }
    tags: tuple[str, ...] = ("platform", "ops", "react")
    # The shared global base prompt (Mermaid output contract) is injected at
    # execution time by the runtime, not baked into this editable template.
    system_prompt_template: str = _SYSTEM_PROMPT

    # Default capability selection projected onto the template's
    # `default_capability_ids` (ADMIN-OPS-AGENTS-RFC §5). Native capability ids
    # are valid entries here — precedent: general_assistant's `document_access`.
    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id="platform_postgres"),
    )

    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System prompt",
            description=(
                "Override the default platform-operations instructions. "
                "Leave blank to use the built-in read-only ops prompt."
            ),
            description_by_lang={
                "fr": (
                    "Remplace les instructions d'exploitation par défaut. "
                    "Laissez vide pour utiliser le prompt intégré en lecture seule."
                )
            },
            required=False,
            default=_SYSTEM_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True, max_lines=12),
        ),
    )

    def policy(self) -> ReActPolicy:
        return ReActPolicy(
            system_prompt_template=self.system_prompt_template,
            # REASON-01 §9 precondition 1 — see fred_agents.tool_pacing.
            tool_selection=REASONING_SAFE_TOOL_SELECTION,
            guardrails=(
                GuardrailDefinition(
                    guardrail_id="ground_on_schema",
                    title="Ground queries on the discovered schema",
                    description=(
                        "List the available tables before the first query of a "
                        "session and never invent tables or columns that the "
                        "discovery tool did not report."
                    ),
                ),
                GuardrailDefinition(
                    guardrail_id="aggregate_in_sql",
                    title="Aggregate in SQL, do not fetch raw rows",
                    description=(
                        "Answer with aggregate queries (GROUP BY, count, avg) "
                        "rather than fetching raw rows; hitting the 200-row cap "
                        "means the query must be rewritten."
                    ),
                ),
                GuardrailDefinition(
                    guardrail_id="fix_failed_queries",
                    title="Fix failed queries, never retry unchanged",
                    description=(
                        "When a query fails, read the server's error message and "
                        "correct the query instead of retrying it unchanged."
                    ),
                ),
            ),
        )


PLATFORM_OPS_AGENT = PlatformOpsReActDefinition()
