# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Generate a short first-turn conversation title with the admitted chat model."""

from __future__ import annotations

import logging
import re

from fred_sdk.contracts.models import AgentDefinition
from langchain_core.messages import HumanMessage, SystemMessage

from ..model_routing import RoutedChatModelFactory
from ..model_routing.turn import current_turn
from ..runtime_context import get_runtime_context
from ..runtime_support.model_metadata import normalize_token_usage

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 600
MAX_TITLE_CHARS = 80
_NOISE = re.compile(r"[^\w\s'-]|_")
_SYSTEM_PROMPT = (
    "You name chat conversations. Reply with the title only: 3 to 8 words, "
    "no quotes, no final punctuation, in the language of the user's message."
)


def _clean(text: str) -> str | None:
    lines = text.strip().splitlines()
    words = _NOISE.sub(" ", lines[0]).split() if lines else []
    title = " ".join(words)[:MAX_TITLE_CHARS].strip("'- ")
    return title if any(char.isalpha() for char in title) else None


async def propose_session_title(
    user_input: str, definition: AgentDefinition
) -> str | None:
    """Return a title when the admitted model answers, without failing the turn."""
    factory = get_runtime_context().config.chat_model_factory
    if not isinstance(factory, RoutedChatModelFactory) or not user_input.strip():
        return None
    try:
        model = factory.build_for_title(definition)
        reply = await model.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=user_input[:MAX_INPUT_CHARS]),
            ]
        )
        if reply.usage_metadata is not None:
            current_turn().record_usage(normalize_token_usage(reply.usage_metadata))
        return _clean(reply.text)
    except Exception as exc:
        logger.warning("event=session_title_failed error=%s", type(exc).__name__)
        return None
