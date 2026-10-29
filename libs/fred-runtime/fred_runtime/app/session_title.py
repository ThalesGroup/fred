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

"""A short conversation title, generated once from the first turn's input.

One bounded call on the pod default model without reasoning; the user owns
the title afterwards.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from ..model_routing import RoutedChatModelFactory
from ..runtime_context import get_runtime_context

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 600
MAX_TITLE_CHARS = 80

_SYSTEM_PROMPT = (
    "You name chat conversations. Reply with the title only: 3 to 8 words, "
    "no quotes, no final punctuation, in the language of the user's message."
)


def _clean(text: str) -> str | None:
    line = text.strip().splitlines()[0] if text.strip() else ""
    line = line.strip().strip("\"'`«»“”").rstrip(".").strip()
    return line[:MAX_TITLE_CHARS] or None


async def propose_session_title(user_input: str) -> str | None:
    """A title for the conversation, or None when no model answers usefully."""
    factory = get_runtime_context().config.chat_model_factory
    if not isinstance(factory, RoutedChatModelFactory) or not user_input.strip():
        return None
    try:
        model, _name, _fallback = factory.build_chat_for_profile(None)
        reply = await model.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(user_input[:MAX_INPUT_CHARS]),
            ]
        )
    except Exception as exc:  # a title is cosmetic: never fail the turn
        logger.warning("event=session_title_failed error=%s", type(exc).__name__)
        return None
    return _clean(reply.text)
