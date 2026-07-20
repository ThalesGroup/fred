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
Conversation history primitives shared across Fred backends.

Why this module exists:
- both ``agentic-backend`` and ``fred-runtime`` (agent pods) need a durable,
  queryable, agent-type-agnostic conversation history store
- the schema and persistence layer must live in ``fred-core`` so that both
  backends can import it without violating the layer rules
  (``fred-runtime`` must not depend on ``agentic-backend``)

How to use it:
- import ``ChatMessage``, ``Role``, ``Channel`` for message construction
- import ``PostgresHistoryStore`` to persist and retrieve messages
- import ``BaseHistoryStore`` to type-annotate store dependencies

Example:
    from fred_core.history import ChatMessage, Role, Channel, PostgresHistoryStore
"""

from fred_core.history.base_history_store import BaseHistoryStore, NoOpHistoryStore
from fred_core.history.history_models import SessionHistoryRow
from fred_core.history.history_schema import (
    Channel,
    ChatMessage,
    ChatMetadata,
    ChatTokenUsage,
    CodePart,
    ImageUrlPart,
    MessagePart,
    Role,
    TextPart,
    ToolCallPart,
    ToolResultPart,
    UiPartRecord,
    make_assistant_final,
    make_tool_call,
    make_tool_result,
    make_user_text,
)
from fred_core.history.postgres_history_store import PostgresHistoryStore

__all__ = [
    "BaseHistoryStore",
    "Channel",
    "ChatMessage",
    "ChatMetadata",
    "ChatTokenUsage",
    "CodePart",
    "ImageUrlPart",
    "MessagePart",
    "NoOpHistoryStore",
    "PostgresHistoryStore",
    "Role",
    "SessionHistoryRow",
    "TextPart",
    "ToolCallPart",
    "ToolResultPart",
    "UiPartRecord",
    "make_assistant_final",
    "make_tool_call",
    "make_tool_result",
    "make_user_text",
]
