from __future__ import annotations

from typing import Any, Dict, Optional

from agentic_backend.core.interrupts.base_interrupt_handler import InterruptHandler


class TemporalInterruptHandler(InterruptHandler):
    """
    Stub for Temporal integration.

    Later we will persist the checkpoint in Temporal (e.g., workflow state / heartbeat)
    and signal the workflow to wait for human input.
    """

    async def handle(
        self,
        *,
        session_id: str,
        exchange_id: str,
        payload: Dict[str, Any],
        checkpoint: Dict[str, Any],
    ) -> None:
        raise NotImplementedError(
            "TemporalInterruptHandler is not implemented yet. "
            "Wire a Temporal-aware handler before enabling HITL in workflows."
        )
