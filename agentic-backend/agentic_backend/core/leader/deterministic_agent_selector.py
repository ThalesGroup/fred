# agentic_backend/core/agents/leader_deterministic_router_picker.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

# Assuming these imports are available from your project structure
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.leader.base_agent_selector import (
    BaseAgentSelector,
    RoutingDecision,
)


@dataclass
class DeterministicAgentSelector(BaseAgentSelector):
    """
    Implements the RouterPicker protocol using deterministic keyword and tag scoring.

    It fulfills the 'choose_and_rephrase' contract by:
    1. Running the scoring logic to find the best expert.
    2. Returning a RoutingDecision where the 'task' is identical to the 'objective'
       (since there is no LLM to perform rephrasing).
    """

    tag_weight: int = 3
    keyword_weight: int = 2
    role_weight: int = 1
    token_cap: int = 64

    def _identity(self, agent: AgentFlow) -> Tuple[str, Tuple[str, ...], str, str]:
        """Extracts settings for scoring using AgentFlow's public methods."""

        name = agent.agent_settings.name
        # Note: get_tags() returns List[str], which is easily converted to a tuple.
        tags = tuple(agent.get_tags())
        role = agent.get_role()
        desc = agent.get_description()

        # Note: If any method returns an empty string or None, your original logic
        # handled that implicitly, but using the getters ensures you get the
        # most accurate, current value.

        return name, tags, role, desc

    def _score_and_sort(
        self,
        objective: str,
        step: str,
        experts: Dict[str, AgentFlow],
        require_tags: Sequence[str] = (),
    ) -> List[str]:
        """
        Internal function based on the old `shortlist` method.
        Returns expert names sorted by calculated score.
        """
        text = (objective + " " + step).lower()
        need = {t.lower() for t in require_tags}

        scored: List[Tuple[int, str]] = []
        for name, agent in experts.items():
            a_name, a_tags, a_role, a_desc = self._identity(agent)

            if need and not need.issubset({t.lower() for t in a_tags}):
                continue

            score = 0
            # Score based on tag presence in the objective/step
            score += self.tag_weight * sum(1 for t in a_tags if t.lower() in text)

            # Score based on keywords in name/role/description
            tokens = (
                (a_name + " " + a_role + " " + a_desc).lower().split()[: self.token_cap]
            )
            seen: set[str] = set()
            deduped = [w for w in tokens if not (w in seen or seen.add(w))]
            score += self.keyword_weight * sum(1 for w in deduped if w in text)

            # Score based on role presence
            if a_role and a_role.lower() in text:
                score += self.role_weight

            if score > 0:
                scored.append((score, name))

        if not scored:
            return sorted(experts.keys())

        # Sort by score (descending) then name (ascending)
        return [n for _, n in sorted(scored, key=lambda x: (-x[0], x[1]))]

    async def choose_and_rephrase(
        self,
        *,
        objective: str,
        experts: Dict[str, AgentFlow],
    ) -> RoutingDecision:
        """
        Selects the best expert deterministically and packages the decision
        into the RoutingDecision structure.
        """
        # 1. Run the scoring logic to get the preferred order
        sorted_names = self._score_and_sort(objective, "", experts)

        if not sorted_names:
            raise ValueError(
                "DeterministicRouterPicker: No experts available or scored."
            )

        # 2. Select the top expert
        chosen_expert_name = sorted_names[0]

        # 3. Formulate the response object
        # Rationale is static since the choice is based on fixed logic.
        rationale = (
            f"Deterministic selection based on highest keyword/tag score relative to the objective."
            f" Expert: {chosen_expert_name}."
        )

        return RoutingDecision(
            expert_name=chosen_expert_name,
            # The task is just the objective, as there's no LLM to rephrase.
            task=objective,
            rationale=rationale,
        )
