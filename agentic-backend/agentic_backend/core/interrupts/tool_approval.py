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
from __future__ import annotations

from typing import Any, Iterable

from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
from agentic_backend.core.interrupts.hitl_i18n import (
    hitl_language_for_agent,
    select_hitl_payload,
)

_HITL_POLICY_EN = (
    "\n\n"
    "Human approval policy:\n"
    "- Some tool calls may require explicit human approval before execution.\n"
    "- When you are about to perform an action that changes state (e.g., create/update/delete/reroute/notify), "
    "briefly explain the action and ask for confirmation.\n"
    "- Read-only tools (get/list/search/track/validate/estimate) can be used without approval."
)

_HITL_POLICY_FR = (
    "\n\n"
    "Politique de validation humaine:\n"
    "- Certains appels d'outils peuvent nécessiter une validation humaine explicite avant exécution.\n"
    "- Lorsque tu vas exécuter une action qui modifie un état (ex: create/update/delete/reroute/notify), "
    "explique brièvement l'action puis demande une confirmation.\n"
    "- Les outils de lecture seule (get/list/search/track/validate/estimate) peuvent être utilisés sans validation."
)

READ_ONLY_TOOL_PREFIXES = (
    "get_",
    "list_",
    "search_",
    "find_",
    "track_",
    "quote_",
    "validate_",
    "estimate_",
    "seed_demo_",
    "read_",
    "describe_",
    "github_",
    "web_",
)

MUTATING_TOOL_PREFIXES = (
    "create_",
    "update_",
    "delete_",
    "remove_",
    "write_",
    "send_",
    "notify_",
    "reroute_",
    "reschedule_",
    "open_",
    "execute_",
    "run_",
    "purge_",
    "revectorize_",
    "build_",
    "drop_",
    "cancel_",
)


def tool_approval_tuning_fields() -> list[FieldSpec]:
    """Shared tuning fields for tool-level HITL approval in ReAct-like agents."""
    return [
        FieldSpec(
            key="safety.enable_tool_approval",
            type="boolean",
            title="Require approval for mutating tools",
            description=(
                "When enabled, the agent interrupts with a HITL confirmation card before executing "
                "tools that look like state-changing actions (e.g., create/reroute/notify/delete)."
            ),
            required=False,
            default=False,
            ui=UIHints(group="Safety"),
        ),
        FieldSpec(
            key="safety.approval_required_tools",
            type="array",
            item_type="string",
            title="Always-approve tool names",
            description=(
                "Optional exact tool names that must always require approval. "
                "Useful for business actions like reroute_package_to_pickup_point."
            ),
            required=False,
            default=[],
            ui=UIHints(group="Safety"),
        ),
    ]


def is_truthy(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return False


def parse_approval_required_tools(raw: Any) -> set[str]:
    if raw is None:
        return set()
    if isinstance(raw, str):
        items = [part.strip() for part in raw.split(",")]
        return {item for item in items if item}
    if isinstance(raw, Iterable):
        names: set[str] = set()
        for item in raw:
            if isinstance(item, str) and item.strip():
                names.add(item.strip())
        return names
    return set()


def requires_tool_approval(
    tool_name: str,
    *,
    approval_enabled: bool,
    exact_required_tools: set[str] | None = None,
) -> bool:
    if not approval_enabled:
        return False

    exact = exact_required_tools or set()
    if tool_name in exact:
        return True

    if tool_name.startswith(READ_ONLY_TOOL_PREFIXES):
        return False

    if tool_name.startswith(MUTATING_TOOL_PREFIXES):
        return True

    return False


def tool_approval_policy_text(agent: Any) -> str:
    return (
        _HITL_POLICY_FR if hitl_language_for_agent(agent) == "fr" else _HITL_POLICY_EN
    )


def tool_approval_ui_payload(agent: Any, tool_name: str) -> dict[str, Any]:
    return select_hitl_payload(
        agent,
        fr={
            "stage": "tool_approval",
            "title": "Confirmer l'exécution de l'outil",
            "question": (
                f"L'agent est sur le point d'exécuter `{tool_name}`, ce qui peut modifier des données "
                "ou déclencher une action. Veux-tu continuer ?"
            ),
            "choices": [
                {
                    "id": "proceed",
                    "label": "Continuer",
                    "description": "Exécuter cet outil maintenant.",
                    "default": True,
                },
                {
                    "id": "cancel",
                    "label": "Annuler",
                    "description": "Ne pas exécuter cet outil et laisser l'agent reformuler ou s'arrêter.",
                },
            ],
        },
        en={
            "stage": "tool_approval",
            "title": "Confirm tool execution",
            "question": (
                f"The agent is about to execute `{tool_name}` which may modify data or trigger an action. "
                "Do you want to proceed?"
            ),
            "choices": [
                {
                    "id": "proceed",
                    "label": "Proceed",
                    "description": "Run this tool now.",
                    "default": True,
                },
                {
                    "id": "cancel",
                    "label": "Cancel",
                    "description": "Do not run this tool; let the agent replan or stop.",
                },
            ],
        },
    )
