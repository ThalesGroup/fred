from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from agentic_backend.core.chatbot.chat_schema import AwaitingHumanEvent
from agentic_backend.core.interrupts.base_interrupt_handler import InterruptHandler

logger = logging.getLogger(__name__)


class StreamingInterruptHandler(InterruptHandler):
    """
    Handle `interrupt()` for the streaming (WebSocket) path.

    - Builds an AwaitingHumanEvent and sends it using the provided `emit` callable.
    - Optionally stores the checkpoint via a `save_checkpoint` callable if provided.
    """

    def __init__(
        self,
        *,
        emit: Callable[[AwaitingHumanEvent], Awaitable[None]],
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
            "[INTERRUPT HANDLER] awaiting_human emit session=%s exchange=%s payload_type=%s payload_keys=%s checkpoint_type=%s checkpoint_keys=%s",
            session_id,
            exchange_id,
            type(payload).__name__,
            list((payload or {}).keys()) if isinstance(payload, dict) else "<non-dict>",
            type(checkpoint).__name__,
            list((checkpoint or {}).keys()) if isinstance(checkpoint, dict) else "<non-dict>",
        )
        if checkpoint is None:
            raise ValueError("checkpoint is required for StreamingInterruptHandler")

        # Persist the checkpoint if a saver is wired.
        if self.save_checkpoint:
            try:
                await self.save_checkpoint(session_id, exchange_id, checkpoint)
            except Exception:  # pragma: no cover - best-effort persistence
                logger.exception("Failed to persist checkpoint for session %s", session_id)

        event = AwaitingHumanEvent(
            session_id=session_id,
            exchange_id=exchange_id,
            payload=payload or {},
        )

        await self.emit(event)
