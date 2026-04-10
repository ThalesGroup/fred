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

"""Standalone ReAct QA definition for DVA Risk Validator Assistant v2.1."""

from __future__ import annotations

from pydantic import Field

from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
from agentic_backend.core.agents.v2 import ToolRefRequirement
from agentic_backend.core.agents.v2.authoring import ReActAgent
from agentic_backend.core.agents.v2.support.builtins import TOOL_REF_KNOWLEDGE_SEARCH

from .prompt_loader import load_dva_risk_validator_prompt

QA_SYSTEM_PROMPT = load_dva_risk_validator_prompt(
    "dva_risk_validator_qa_system_prompt.md"
)


def _qa_fields() -> tuple[FieldSpec, ...]:
    """
    Build author-facing QA configuration surface.

    Why this exists:
    - QA agent is standalone and must explicitly expose chat options for runtime scoping

    How to use:
    - keep the `chat_options.*` defaults enabled to preserve DVA/report/index retrieval

    Example:
    ```python
    fields = _qa_fields()
    ```
    """

    return (
        FieldSpec(
            key="system_prompt_template",
            type="prompt",
            title="System prompt",
            description="Grounding instructions for DVA follow-up QA.",
            required=True,
            default=QA_SYSTEM_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="chat_options.attach_files",
            type="boolean",
            title="Attachments",
            description="Allow QA turns to include additional attachment evidence.",
            required=False,
            default=True,
            ui=UIHints(group="agentTuning.groups.chatOptions"),
        ),
        FieldSpec(
            key="chat_options.libraries_selection",
            type="boolean",
            title="Library selection",
            description="Allow QA turns to restrict retrieval to selected libraries.",
            required=False,
            default=True,
            ui=UIHints(group="agentTuning.groups.chatOptions"),
        ),
        FieldSpec(
            key="chat_options.documents_selection",
            type="boolean",
            title="Document selection",
            description="Allow QA turns to restrict retrieval to selected documents.",
            required=False,
            default=True,
            ui=UIHints(group="agentTuning.groups.chatOptions"),
        ),
        FieldSpec(
            key="chat_options.search_rag_scoping",
            type="boolean",
            title="RAG scope",
            description="Allow QA turns to pick corpus/session/general retrieval scope.",
            required=False,
            default=True,
            ui=UIHints(group="agentTuning.groups.chatOptions"),
        ),
    )


class DVARiskValidatorQA(ReActAgent):
    """
    Follow-up QA agent grounded on DVA + generated validation artifacts.

    This definition is dedicated to DVA risk follow-up questions and is not a
    profile-only alias of the generic ReAct family.
    """

    agent_id: str = "production.dva_risk_validator.qa"
    role: str = "DVA Risk Validator (QA)"
    description: str = (
        "Grounded follow-up QA over original DVA content and generated "
        "validation report/index artifacts."
    )
    tags: tuple[str, ...] = (
        "dva",
        "risk",
        "validator",
        "qa",
        "react",
        "production",
        "v2",
    )

    system_prompt_template: str = Field(default=QA_SYSTEM_PROMPT, min_length=1)
    fields: tuple[FieldSpec, ...] = _qa_fields()
    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            description=(
                "Search scoped DVA/report/index sources before answering factual "
                "follow-up questions."
            ),
        ),
    )
