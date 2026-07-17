"""Kea→Swift agent template mapping (MIGR-05).

Maps a kea-exported agent to its swift template, so the import can create the
equivalent managed `agent_instance`. Kea-import-path only (§8 of
docs/swift/rfc/PLATFORM-IMPORT-RFC.md) — swift-native imports carry
`agent_instance` rows directly and never go through this mapping.

The mapping table is the single control point. Every exported agent is classified
into exactly one outcome:

- ``MAPPED``  — the kea template has a swift equivalent; create the agent_instance.
- ``IGNORED`` — a known kea built-in sample/demo; not user data, skipped on purpose.
- ``GAP``     — no mapping yet (or no resolvable template); the equivalent must be
  built in fred-agents and added here. A real cutover requires zero gaps.

Scope is user-created agent instances; kea sample agents are intentionally not
migrated (swift provides its own catalog).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# Kea template identity → swift template id (``{source_runtime_id}:{source_agent_id}``).
# Keys are a v2 ``definition_ref`` or a legacy v1 ``class_path``. Swift ids are
# validated at import time against the live fred-agents ``/agents/templates`` catalog.
KEA_TO_SWIFT_TEMPLATE: dict[str, str] = {
    # Agents users actually create on kea:
    "v2.react.basic": "fred-agents:fred.github.assistant",
    "v2.production.sql_analyst": "fred-agents:fred.github.sql_expert",
    # Equivalents available if a real user instance uses them:
    "agentic_backend.agents.v1.production.prometheus.prometheus_expert.Spot": "fred-agents:fred.github.sentinel",
    "agentic_backend.agents.v1.production.rags.rag_expert.Rico": "fred-agents:fred.github.rag_expert",
    "agentic_backend.agents.v1.production.tabular.tabular_expert.Tessa": "fred-agents:fred.github.sql_expert",
}

# Kea built-in sample/demo templates that are intentionally NOT migrated. Listed so
# preflight treats them as expected rather than as gaps requiring a new fred-agents
# template.
IGNORED_KEA_TEMPLATES: frozenset[str] = frozenset(
    {
        "v2.sample.bank_transfer",
        "v2.deep.corpus_investigator",
        "v2.production.dva_risk_validator.graph",
        "v2.production.dva_risk_validator.qa",
    }
)


class AgentMapOutcome(str, Enum):
    """How an exported kea agent is treated by the import."""

    MAPPED = "mapped"
    IGNORED = "ignored"
    GAP = "gap"


@dataclass(frozen=True)
class AgentMapResult:
    """Result of classifying one exported kea agent.

    ``kea_template`` is the resolved template identity (``None`` when neither a
    ``definition_ref`` nor a ``class_path`` is present). ``swift_template_id`` is set
    only when ``outcome`` is ``MAPPED``.
    """

    outcome: AgentMapOutcome
    kea_template: str | None
    swift_template_id: str | None


def resolve_kea_template(payload: Mapping[str, Any]) -> str | None:
    """Return the kea template identity from an exported agent ``payload_json``.

    v2 agents carry a top-level ``definition_ref``; legacy v1 agents carry a
    top-level ``class_path``. ``definition_ref`` takes precedence. Returns ``None``
    when neither is present (the agent is then a GAP).
    """
    definition_ref = payload.get("definition_ref")
    if isinstance(definition_ref, str) and definition_ref.strip():
        return definition_ref
    class_path = payload.get("class_path")
    if isinstance(class_path, str) and class_path.strip():
        return class_path
    return None


def classify_agent(payload: Mapping[str, Any]) -> AgentMapResult:
    """Classify one exported kea agent ``payload_json`` into mapped / ignored / gap.

    The agent is MAPPED when its template is in ``KEA_TO_SWIFT_TEMPLATE``, IGNORED
    when it is a known sample, and a GAP otherwise (including when no template can be
    resolved). Each GAP is a fred-agents template to build before cutover.
    """
    kea_template = resolve_kea_template(payload)
    if kea_template is None:
        return AgentMapResult(AgentMapOutcome.GAP, None, None)
    swift_template_id = KEA_TO_SWIFT_TEMPLATE.get(kea_template)
    if swift_template_id is not None:
        return AgentMapResult(AgentMapOutcome.MAPPED, kea_template, swift_template_id)
    if kea_template in IGNORED_KEA_TEMPLATES:
        return AgentMapResult(AgentMapOutcome.IGNORED, kea_template, None)
    return AgentMapResult(AgentMapOutcome.GAP, kea_template, None)
