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
Author-facing models a Knowledge Base synchronization handler receives and
returns. Everything here is JSON-safe: `model_dump(mode="json")` round-trips.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    computed_field,
    field_validator,
    model_validator,
)

from fred_sdk.contracts.models import TuningValue

# Bounds on the free-form parts of a run result. No repository-wide canonical
# values exist, so these are deliberately conservative: a result is a summary
# for an operator, never a transport for the run's output.
MAX_SUMMARY_CHARS = 2_000
MAX_ISSUE_MESSAGE_CHARS = 500
MAX_ISSUE_SUBJECT_CHARS = 200
MAX_ISSUES = 50


def _clip(value: str, bound: int) -> tuple[str, bool]:
    """Return the value cut to `bound`, and whether cutting removed anything."""
    return value[:bound], len(value) > bound


class KnowledgeBaseRunOutcome(StrEnum):
    """Terminal outcome of one synchronization run.

    Orthogonal to `KnowledgeBaseSyncResult.reconciliation_complete`: a run can
    succeed having deliberately covered only part of its source.
    """

    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class KnowledgeBaseIssue(BaseModel):
    """One warning or error a run reports, with a stable machine-readable code.

    Severity is carried by which list it lands in — `warnings` or `errors` —
    never by a field here. `subject` stays deliberately generic: it names what
    the issue is about in the implementation's own terms, and is not a path.
    """

    code: str = Field(min_length=1, max_length=100)
    message: str = ""
    subject: str | None = Field(
        default=None,
        description=(
            "What this issue concerns, in the implementation's own vocabulary. "
            "Opaque to Fred, which never parses or resolves it."
        ),
    )

    # Bounds are applied by the result that carries this issue, not here: a
    # private flag set on an issue does not survive the parent's validation.


class KnowledgeBaseRunContext(BaseModel):
    """What a synchronization handler is told about the run it is serving.

    Carries stable identifiers and the instance's resolved configuration —
    never a credential for Fred, a transport client, or any platform object.

    Configuration is validated against the definition's declared fields by the
    Control Plane that dispatches the run, not by this type: a context built by
    hand carries whatever it was given.
    """

    definition_id: str = Field(min_length=1)
    instance_id: str = Field(min_length=1)
    team_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    configuration: dict[str, TuningValue] = Field(default_factory=dict)


class KnowledgeBaseSyncResult(BaseModel):
    """What a synchronization handler reports back about one run.

    Counters are generic on purpose so any source populates them honestly;
    anything source-specific belongs in `metrics`.

    `removed` counts retractions the implementation actually carried out
    through the document boundary. It is a report, never an instruction: Fred
    does not delete anything by reading this number. An absence in a source
    proves a deletion only after a complete, authoritative inventory — which is
    exactly what `reconciliation_complete` states — whereas an explicit
    tombstone stays actionable even during a partial pass.
    """

    outcome: KnowledgeBaseRunOutcome
    reconciliation_complete: bool = Field(
        description=(
            "True only when this run observed the source exhaustively and "
            "authoritatively. False marks a valid but bounded pass — paging cut "
            "short, a filter applied, a budget reached — after which an absence "
            "proves nothing about deletion."
        ),
    )
    summary: str = ""
    discovered: int = Field(default=0, ge=0)
    created: int = Field(default=0, ge=0)
    updated: int = Field(default=0, ge=0)
    removed: int = Field(default=0, ge=0)
    unchanged: int = Field(default=0, ge=0)
    warnings: list[KnowledgeBaseIssue] = Field(default_factory=list)
    errors: list[KnowledgeBaseIssue] = Field(default_factory=list)
    metrics: dict[str, Any] | None = None

    model_config = ConfigDict(populate_by_name=True)

    # Accepted on input so the flag survives the wire to Fred, but only ever
    # OR-ed with what this pass actually clipped: it can be raised, never lowered.
    truncated_upstream: bool = Field(
        default=False, alias="content_truncated", exclude=True
    )

    _truncated: bool = PrivateAttr(default=False)

    @model_validator(mode="after")
    def _bound_free_form_content(self) -> "KnowledgeBaseSyncResult":
        # Clip and record in one pass: re-measuring an already-clipped value
        # cannot tell "exactly at the bound" from "cut down to it".
        clipped = self.truncated_upstream
        self.summary, summary_clipped = _clip(self.summary, MAX_SUMMARY_CHARS)
        clipped = clipped or summary_clipped
        dropped = len(self.warnings) > MAX_ISSUES or len(self.errors) > MAX_ISSUES
        self.warnings = self.warnings[:MAX_ISSUES]
        self.errors = self.errors[:MAX_ISSUES]

        for issue in (*self.warnings, *self.errors):
            issue.message, message_clipped = _clip(
                issue.message, MAX_ISSUE_MESSAGE_CHARS
            )
            clipped = clipped or message_clipped
            if issue.subject is not None:
                issue.subject, subject_clipped = _clip(
                    issue.subject, MAX_ISSUE_SUBJECT_CHARS
                )
                clipped = clipped or subject_clipped

        self._truncated = clipped or dropped
        return self

    @field_validator("metrics")
    @classmethod
    def _require_json_safe(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return value
        try:
            json.dumps(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"metrics must be JSON-safe: {exc}") from exc
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_truncated(self) -> bool:
        """Whether any free-form content in this result was shortened.

        Raised by whatever clipping this pass did, OR-ed with an incoming
        `content_truncated` so the flag survives serialization to Fred. It can
        never be lowered: an implementation asserting nothing was truncated
        while returning clipped content still reports true.
        """
        return self._truncated
