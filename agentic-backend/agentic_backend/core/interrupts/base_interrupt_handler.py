# Copyright Thales 2025
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
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class InterruptHandler(ABC):
    """
    Minimal abstraction to handle LangGraph `interrupt()` signals.

    IN order not to be confused: a langraph agent that requires human input
    will call `interrupt()` on its graph node. This invokes the handler wired
    into the agent's runtime context. Behind the scenes, the handler is responsible
    for dealing with the interrupt event either as part of a real time streaming
    session (e.g., via WebSocket) or as part of a Temporal workflow (e.g., via
    workflow signaling).

    Why not HumanInTheLoopMiddleware directly?
    - LangChain's HumanInTheLoopMiddleware is tightly coupled to synchronous
      execution and does not fit well with our async agent flows.
    - We want to keep the agent code free of Temporal dependencies.

    A HumanInTheLoopMiddleware is a better fit for react style agents where
    the agent itself manages tool calls and interruptions. In contrast, our
    LangGraph agents delegate tool calls to the graph runtime, which makes
    InterruptHandler a more natural fit.

    Implementations decide how to persist the checkpoint and how to notify
    the caller (WebSocket, Temporal, etc.).
    """

    @abstractmethod
    async def handle(
        self,
        *,
        session_id: str,
        exchange_id: str,
        payload: Dict[str, Any],
        checkpoint: Dict[str, Any],
    ) -> None:
        """
        Args:
            session_id: current chat session identifier.
            exchange_id: current exchange (message turn) identifier.
            payload: the dict passed to `interrupt(...)` by the agent node.
            checkpoint: serialized graph state (required to resume).
        """
        ...
