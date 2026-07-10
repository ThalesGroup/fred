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
Shared helper for the ReAct platform middleware frame (#1972).

Why this module exists:
- several middleware in the frame read the raw checkpointed message history the
  same way; keeping that single reader here avoids duplicating the logic per
  middleware module.
"""

from __future__ import annotations

from typing import Any


def state_messages(state_like: object) -> list[Any]:
    """
    Read the raw (unsanitized) message history from one agent state mapping.

    Why this exists:
    - routing, prompt, tracing, and HITL decisions are all made against the RAW
      checkpointed history, exactly as the legacy `reasoner`/`gate_tools` nodes
      did; only the model input goes through hygiene

    How to use:
    - pass `request.state` or the `after_model` state argument
    """

    messages = state_like.get("messages", []) if isinstance(state_like, dict) else []
    return messages if isinstance(messages, list) else []
