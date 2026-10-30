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

One bounded call without reasoning; the user owns the title afterwards.
"""

from __future__ import annotations

import logging
import re

from fred_sdk.contracts.context import ModelBinding
from langchain_core.messages import HumanMessage, SystemMessage

from ..model_routing import RoutedChatModelFactory
from ..runtime_context import get_runtime_context

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 600
MAX_TITLE_CHARS = 80
# Everything but letters, digits, spaces, apostrophes and hyphens.
_NOISE = re.compile(r"[^\w\s'’-]|_")

_SYSTEM_PROMPT = (
    "You name chat conversations. Reply with the title only: 3 to 8 words, "
    "no quotes, no final punctuation, in the language of the user's message."
)


def _clean(text: str) -> str | None:
    lines = text.strip().splitlines()
    words = _NOISE.sub(" ", lines[0]).split() if lines else []
    title = " ".join(words)[:MAX_TITLE_CHARS].strip("'’- ")
    return title if any(char.isalpha() for char in title) else None


async def propose_session_title(
    user_input: str,
    *,
    profile_id: str | None = None,
    binding: ModelBinding | None = None,
) -> str | None:
    """A title for the conversation, or None when no model answers usefully.

    Uses the admin's title model, else the platform chat binding, else the pod
    default."""
    factory = get_runtime_context().config.chat_model_factory
    if not isinstance(factory, RoutedChatModelFactory) or not user_input.strip():
        return None
    try:
        if binding is not None and profile_id is None:
            model = factory.build_chat_for_binding(binding)
        else:
            model, _name, _fallback = factory.build_chat_for_profile(profile_id)
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
