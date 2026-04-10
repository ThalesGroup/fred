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

"""Graph definition for DVA Risk Validator Assistant v2.1."""

from __future__ import annotations

from pydantic import BaseModel

from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
from agentic_backend.core.agents.v2 import GraphExecutionOutput, ToolRefRequirement
from agentic_backend.core.agents.v2.graph.authoring import GraphAgent, GraphWorkflow
from agentic_backend.core.agents.v2.support.builtins import TOOL_REF_KNOWLEDGE_SEARCH

from .graph_state import DVARiskValidatorInput, DVARiskValidatorState
from .graph_steps import (
    ask_max_risk_count_step,
    build_report_step,
    enrich_to_requested_count_step,
    extract_source_risks_step,
    finalize_step,
    locate_risk_table_step,
    maybe_ask_risk_section_step,
    persist_session_scope_step,
    publish_outputs_step,
    recommend_actions_mitigations_step,
    recommend_strategy_step,
    retrieve_coverage_evidence_step,
    route_or_start_step,
    validate_treatment_step,
)


def _chat_option_fields() -> tuple[FieldSpec, ...]:
    """
    Build explicit chat option field specs required by runtime scoping.

    Why this exists:
    - this graph is not profile-driven; it must expose chat options directly
    - these keys drive attachment/library/document/RAG scope controls in runtime UI

    How to use:
    - keep these defaults at `True` unless the business workflow removes support

    Example:
    ```python
    fields = _chat_option_fields()
    ```
    """

    return (
        FieldSpec(
            key="chat_options.attach_files",
            type="boolean",
            title="Attachments",
            description="Allow users to attach files used by DVA validation retrieval.",
            required=False,
            default=True,
            ui=UIHints(group="agentTuning.groups.chatOptions"),
        ),
        FieldSpec(
            key="chat_options.libraries_selection",
            type="boolean",
            title="Library selection",
            description="Allow users to select document libraries for this validation run.",
            required=False,
            default=True,
            ui=UIHints(group="agentTuning.groups.chatOptions"),
        ),
        FieldSpec(
            key="chat_options.documents_selection",
            type="boolean",
            title="Document selection",
            description="Allow users to scope validation to explicit document UIDs.",
            required=False,
            default=True,
            ui=UIHints(group="agentTuning.groups.chatOptions"),
        ),
        FieldSpec(
            key="chat_options.search_rag_scoping",
            type="boolean",
            title="RAG scope",
            description="Allow users to choose corpus/session/general retrieval scope.",
            required=False,
            default=True,
            ui=UIHints(group="agentTuning.groups.chatOptions"),
        ),
    )


class DVARiskValidatorGraph(GraphAgent):
    """
    Workflow-shaped DVA Risk Validator assistant (v2.1).

    This agent validates risk treatment evidence, generates recommendations,
    publishes report artifacts, and prepares retrieval scope for follow-up QA.
    """

    agent_id: str = "production.dva_risk_validator.graph"
    role: str = "DVA Risk Validator (Graph)"
    description: str = (
        "Graph workflow that validates DVA risks, treatment evidence, blockers, "
        "and inferred mitigation recommendations with report/index artifacts."
    )
    tags: tuple[str, ...] = ("dva", "risk", "validator", "graph", "production", "v2")

    fields: tuple[FieldSpec, ...] = _chat_option_fields()
    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            description=(
                "Retrieve DVA evidence in current runtime scope. "
                "Payload is limited to query/top_k; scope comes from RuntimeContext."
            ),
        ),
    )

    input_schema = DVARiskValidatorInput
    state_schema = DVARiskValidatorState
    input_to_state = {"message": "latest_user_text"}
    output_state_field = "final_text"

    workflow = GraphWorkflow(
        entry="route_or_start",
        nodes={
            "route_or_start": route_or_start_step,
            "ask_max_risk_count": ask_max_risk_count_step,
            "locate_risk_table": locate_risk_table_step,
            "maybe_ask_risk_section": maybe_ask_risk_section_step,
            "extract_source_risks": extract_source_risks_step,
            "enrich_to_requested_count": enrich_to_requested_count_step,
            "retrieve_coverage_evidence": retrieve_coverage_evidence_step,
            "validate_treatment": validate_treatment_step,
            "recommend_strategy": recommend_strategy_step,
            "recommend_actions_mitigations": recommend_actions_mitigations_step,
            "build_report": build_report_step,
            "publish_outputs": publish_outputs_step,
            "persist_session_scope": persist_session_scope_step,
            "finalize": finalize_step,
        },
        edges={
            "extract_source_risks": "enrich_to_requested_count",
            "enrich_to_requested_count": "retrieve_coverage_evidence",
            "retrieve_coverage_evidence": "validate_treatment",
            "validate_treatment": "recommend_strategy",
            "recommend_strategy": "recommend_actions_mitigations",
            "recommend_actions_mitigations": "build_report",
            "build_report": "publish_outputs",
            "publish_outputs": "persist_session_scope",
            "persist_session_scope": "finalize",
        },
        routes={
            "route_or_start": {
                "start": "ask_max_risk_count",
            },
            "ask_max_risk_count": {
                "valid": "locate_risk_table",
                "retry": "ask_max_risk_count",
            },
            "locate_risk_table": {
                "found": "extract_source_risks",
                "missing": "maybe_ask_risk_section",
            },
            "maybe_ask_risk_section": {
                "continue": "extract_source_risks",
            },
        },
    )

    def build_output(self, state: BaseModel) -> BaseModel:
        """
        Build final graph output including UI download links.

        Why this exists:
        - graph chat output must include report body and standard artifact link parts

        How to use:
        - runtime calls this automatically at graph completion

        Example:
        ```python
        output = definition.build_output(state)
        ```
        """

        typed_state = DVARiskValidatorState.model_validate(state)
        ui_parts = []
        if typed_state.result_artifact is not None:
            ui_parts.append(typed_state.result_artifact.to_link_part())
        if typed_state.risk_index_artifact is not None:
            ui_parts.append(typed_state.risk_index_artifact.to_link_part())
        return GraphExecutionOutput(
            content=typed_state.final_text,
            ui_parts=tuple(ui_parts),
        )
