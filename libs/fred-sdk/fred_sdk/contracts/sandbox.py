# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""One-shot isolated code execution contract shared by agents and brokers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SandboxLanguage = Literal["bash", "python"]


class SandboxRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    language: SandboxLanguage
    code: str = Field(min_length=1, max_length=16_384)


class SandboxResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    exit_code: int | None
    stdout: str = Field(max_length=16_384)
    stderr: str = Field(max_length=16_384)
    timed_out: bool = False
    truncated: bool = False


class SandboxError(RuntimeError):
    """A bounded failure code that is safe to surface to an agent."""

    _allowed = frozenset(
        {
            "unavailable",
            "unauthorized",
            "busy",
            "invalid_request",
            "runtime_unavailable",
            "policy_unavailable",
            "backend_failed",
            "invalid_response",
        }
    )

    def __init__(self, code: str) -> None:
        self.code = code if code in self._allowed else "unavailable"
        super().__init__(self.code)


class SandboxExecutionPort(ABC):
    @abstractmethod
    async def execute(self, request: SandboxRequest) -> SandboxResult:
        """Run source in an isolated workload; infrastructure is bound privately."""
