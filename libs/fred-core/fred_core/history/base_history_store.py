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
Abstract base and no-op implementations for conversation history stores.

Why this module exists:
- both ``agentic-backend`` and ``fred-runtime`` pods need a stable interface for
  writing and reading conversation history
- the abstract base lives in ``fred-core`` so that either backend can type-annotate
  store dependencies without importing the concrete Postgres implementation
- ``NoOpHistoryStore`` lets tests exercise agent orchestration without any DB setup

How to use it:
- inject ``BaseHistoryStore`` as a type annotation in code that writes or reads history
- use ``NoOpHistoryStore`` in offline unit tests where persistence is not under test
- use ``PostgresHistoryStore`` (in ``postgres_history_store``) in production

Example:
    from fred_core.history.base_history_store import BaseHistoryStore

    class MyService:
        def __init__(self, history: BaseHistoryStore) -> None:
            self._history = history
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from fred_core.history.history_schema import ChatMessage


class BaseHistoryStore(ABC):
    """
    Abstract conversation history store.

    All implementations must support:
    - ``save``: persist a batch of messages for one turn
    - ``get``: retrieve all messages for a session, ordered by rank
    - ``list_sessions``: return distinct session IDs for a user, most recent first
    """

    @abstractmethod
    async def save(
        self,
        session_id: str,
        messages: List[ChatMessage],
        user_id: str,
        team_id: str | None = None,
        agent_instance_id: str | None = None,
    ) -> None:
        """
        Persist a batch of messages for one turn.

        Why batching:
        - a single user turn produces several messages (user input, assistant
          response, tool calls, tool results) that must be written atomically
          to keep the rank sequence consistent

        How to use it:
        - call once per turn after the executor generator is exhausted
        - messages must already have ``rank`` set in ascending order
        - team_id and agent_instance_id are required for admin/retention queries;
          pass them whenever the execution context is managed (Phase 3c+)
        """

    @abstractmethod
    async def get(
        self,
        session_id: str,
    ) -> List[ChatMessage]:
        """
        Retrieve all messages for a session, ordered by rank ascending.

        How to use it:
        - call from the ``GET /sessions/{session_id}/messages`` endpoint
        - returns an empty list when no rows exist for the session
        """

    @abstractmethod
    async def list_sessions(
        self,
        user_id: str,
    ) -> List[str]:
        """
        Return distinct session IDs for a user, ordered by most recent first.

        Why this exists:
        - the UI needs to list past conversations for a returning user
        - the checkpointer has no ``user_id`` index; only the history store does

        How to use it:
        - call from the ``GET /sessions?user_id=<user_id>`` endpoint
        """


class NoOpHistoryStore(BaseHistoryStore):
    """
    History store that accepts writes but never persists anything.

    Why this exists:
    - tests that exercise agent orchestration or tool execution should not couple
      to persistence; this store satisfies the interface while remaining stateless
    - also used when no storage backend is configured (stateless pod mode)

    How to use it:
    - inject in place of ``PostgresHistoryStore`` in offline unit tests
    - ``get`` always returns an empty list; ``list_sessions`` always returns []
    """

    async def save(
        self,
        session_id: str,
        messages: List[ChatMessage],
        user_id: str,
        team_id: str | None = None,
        agent_instance_id: str | None = None,
    ) -> None:
        return

    async def get(
        self,
        session_id: str,
    ) -> List[ChatMessage]:
        return []

    async def list_sessions(
        self,
        user_id: str,
    ) -> List[str]:
        return []
