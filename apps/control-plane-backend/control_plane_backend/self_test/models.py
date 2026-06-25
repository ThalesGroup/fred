from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class StepStatus(StrEnum):
    """Per-step verdict. Maps cleanly onto the frontend Task/Event state atoms."""

    pending = "pending"
    running = "running"
    passed = "passed"
    failed = "failed"
    skipped = "skipped"

    @property
    def is_terminal(self) -> bool:
        return self in (StepStatus.passed, StepStatus.failed, StepStatus.skipped)


class RunState(StrEnum):
    running = "running"
    passed = "passed"
    failed = "failed"


class StepResult(BaseModel):
    """One ordered validation step within a campaign run."""

    id: str
    title: str
    status: StepStatus = StepStatus.pending
    detail: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None


class SelfTestRun(BaseModel):
    """Snapshot of a campaign run: ordered steps plus an overall verdict."""

    run_id: str
    state: RunState = RunState.running
    team_id: str
    steps: list[StepResult] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime | None = None

    @property
    def total(self) -> int:
        return len(self.steps)

    @property
    def completed(self) -> int:
        return sum(1 for s in self.steps if s.status.is_terminal)

    @property
    def progress(self) -> float | None:
        return self.completed / self.total if self.total else None


class SelfTestEvent(BaseModel):
    """SSE payload streamed on each step transition.

    Shape is intentionally close to fred_core TaskEvent so the frontend Task
    atoms can render it: a current ``step`` label, a 0..1 ``progress``, and an
    overall ``state``. The full ``steps`` list lets a late subscriber render the
    whole sequence without replay.
    """

    run_id: str
    state: RunState
    seq: int
    progress: float | None = None
    step: str | None = None
    steps: list[StepResult] = Field(default_factory=list)


class StartSelfTestResponse(BaseModel):
    run_id: str
