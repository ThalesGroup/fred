from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from agentic_backend.core.chatbot.chat_schema import validate_hitl_payload
from agentic_backend.core.interrupts.base_interrupt_handler import InterruptHandler
from agentic_backend.scheduler.agent_contracts import HumanInputRequestEventV1

logger = logging.getLogger(__name__)


class TemporalInterruptHandler(InterruptHandler):
    """
    Handle `interrupt()` for Temporal workflows.

    - Validates the HITL payload using the same schema as streaming.
    - Persists the checkpoint (so resume is possible) if a saver is wired.
    - Emits a `HumanInputRequestEventV1` that the activity can heartbeat/signal.
    """

    def __init__(
        self,
        *,
        emit: Callable[[HumanInputRequestEventV1], Awaitable[None]],
        save_checkpoint: Optional[
            Callable[[str, str, Dict[str, Any]], Awaitable[None]]
        ] = None,
    ):
        self.emit = emit
        self.save_checkpoint = save_checkpoint

    async def handle(
        self,
        *,
        session_id: str,
        exchange_id: str,
        payload: Dict[str, Any],
        checkpoint: Dict[str, Any],
    ) -> None:
        logger.info(
            "[TEMPORAL INTERRUPT] session=%s exchange=%s payload_type=%s checkpoint_keys=%s",
            session_id,
            exchange_id,
            type(payload).__name__,
            list((checkpoint or {}).keys()) if isinstance(checkpoint, dict) else None,
        )

        if checkpoint is None:
            raise ValueError("checkpoint is required for TemporalInterruptHandler")

        # Validate and normalize payload (shared schema with streaming path)
        validated = validate_hitl_payload(payload or {})

        # Persist checkpoint if wired; best-effort.
        if self.save_checkpoint:
            try:
                await self.save_checkpoint(session_id, exchange_id, checkpoint)
            except Exception:  # pragma: no cover - best-effort persistence
                logger.exception(
                    "Failed to persist checkpoint for session %s (Temporal path)",
                    session_id,
                )

        # Derive an interaction identifier; prefer explicit checkpoint_id, else exchange/session.
        checkpoint_id = (
            validated.checkpoint_id
            or (checkpoint.get("id") if isinstance(checkpoint, dict) else None)
            or (
                checkpoint.get("checkpoint_id")
                if isinstance(checkpoint, dict)
                else None
            )
            or exchange_id
        )

        input_schema = {
            "stage": validated.stage,
            "title": validated.title,
            "question": validated.question,
            "choices": [c.model_dump(exclude_none=True) for c in validated.choices]
            if validated.choices
            else None,
            "free_text": validated.free_text,
            "metadata": validated.metadata,
        }
        # Drop empty entries to keep the schema concise.
        input_schema = {
            k: v for k, v in input_schema.items() if v not in (None, [], {})
        }

        event = HumanInputRequestEventV1(
            interaction_id=str(checkpoint_id),
            prompt=validated.question or validated.title or "Human input requested",
            input_schema=input_schema,
            extras={
                "session_id": session_id,
                "exchange_id": exchange_id,
                "checkpoint_id": checkpoint_id,
                "raw_payload": validated.model_dump(exclude_none=True),
            },
        )

        await self.emit(event)
