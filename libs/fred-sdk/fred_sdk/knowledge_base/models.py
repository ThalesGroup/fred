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

from pydantic import BaseModel, Field, field_validator

from fred_sdk.contracts.models import TuningValue

# Bounds on the free-form parts of a run result. No repository-wide canonical
# values exist, so these are deliberately conservative: a result is a summary
# for an operator, never a transport for the run's output.
MAX_SUMMARY_CHARS = 2_000
MAX_ISSUE_MESSAGE_CHARS = 500
MAX_ISSUES = 50


class KnowledgeBaseRunOutcome(StrEnum):
    """Terminal outcome of one synchronization run."""

    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class KnowledgeBaseIssue(BaseModel):
    """One warning or error a run reports, with a stable machine-readable code."""

    code: str = Field(min_length=1, max_length=100)
    message: str = ""

    @field_validator("message")
    @classmethod
    def _bound_message(cls, value: str) -> str:
        return value[:MAX_ISSUE_MESSAGE_CHARS]


class KnowledgeBaseRunContext(BaseModel):
    """What a synchronization handler is told about the run it is serving.

    Carries stable identifiers and the instance's resolved configuration —
    never a credential for Fred, a transport client, or any platform object.
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
    """

    outcome: KnowledgeBaseRunOutcome
    summary: str = ""
    discovered: int = Field(default=0, ge=0)
    created: int = Field(default=0, ge=0)
    updated: int = Field(default=0, ge=0)
    removed: int = Field(default=0, ge=0)
    unchanged: int = Field(default=0, ge=0)
    warnings: list[KnowledgeBaseIssue] = Field(default_factory=list)
    errors: list[KnowledgeBaseIssue] = Field(default_factory=list)
    metrics: dict[str, Any] | None = None

    @field_validator("summary")
    @classmethod
    def _bound_summary(cls, value: str) -> str:
        return value[:MAX_SUMMARY_CHARS]

    @field_validator("warnings", "errors")
    @classmethod
    def _bound_issues(cls, value: list[KnowledgeBaseIssue]) -> list[KnowledgeBaseIssue]:
        return value[:MAX_ISSUES]

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
