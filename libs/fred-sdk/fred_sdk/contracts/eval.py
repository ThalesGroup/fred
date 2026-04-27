from __future__ import annotations

from fred_sdk.contracts.runtime import FrozenModel
from pydantic import Field


class EvalStep(FrozenModel):
    kind: str = Field(..., min_length=1)

    tool_name: str | None = None
    call_id: str | None = None
    arguments: dict[str, object] | None = None

    content: str | None = None
    is_error: bool | None = None

    node_id: str | None = None
    error_message: str | None = None


class EvalTrace(FrozenModel):
    session_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    input: str = Field(..., min_length=1)

    output: str | None = None
    error: str | None = None
    latency_ms: int = Field(..., ge=0)

    model_name: str | None = None
    token_usage: dict[str, int] | None = None
    finish_reason: str | None = None

    steps: tuple[EvalStep, ...] = ()
