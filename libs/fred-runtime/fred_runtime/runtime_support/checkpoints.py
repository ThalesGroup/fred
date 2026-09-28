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
Typed async checkpoint access helpers for Fred v2.

Why this file exists:
- Fred decided to treat checkpoint persistence as async-only in real v2 paths.
- Resume and interrupt handling should not probe saver objects with
  `hasattr(...)` branches.
- Both the legacy LangGraph `MemorySaver` and Fred's v2 SQL saver already
  support the async `aget_tuple(...)` contract, so that contract should be the
  only one Fred code relies on.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

from fred_sdk.contracts.execution import SESSION_ID_RESERVED_CHAR, check_session_id
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata, PendingWrite


class CheckpointTupleLike(Protocol):
    checkpoint: Checkpoint
    pending_writes: list[PendingWrite] | None


class AsyncCheckpointReader(Protocol):
    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTupleLike | None:
        raise NotImplementedError()


class AsyncCheckpointWriter(AsyncCheckpointReader, Protocol):
    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Mapping[str, str | int | float],
    ) -> RunnableConfig:
        raise NotImplementedError()


def checkpoint_config(*, thread_id: str, checkpoint_ns: str = "") -> RunnableConfig:
    configurable: dict[str, object] = {
        "thread_id": thread_id,
        "checkpoint_ns": checkpoint_ns,
    }
    return cast(RunnableConfig, {"configurable": configurable})


def graph_thread_id(session_id: str, namespace: str) -> str:
    """
    Thread id of a LangGraph-native graph agent for one session.

    LangGraph stores every root run at checkpoint_ns "", so the agent namespace
    moves into the thread id; an in-process sub-agent sharing the session then
    never shares the caller's thread. The session id stays the prefix so a
    session purge finds these threads (`graph_thread_prefix`).
    """
    return f"{graph_thread_prefix(session_id)}{namespace}"


def graph_thread_prefix(session_id: str) -> str:
    check_session_id(session_id)
    return f"{session_id}{SESSION_ID_RESERVED_CHAR}"


def checkpoint_namespace(
    *,
    agent_instance_id: str | None,
    agent_id: str,
) -> str:
    """
    Return the LangGraph checkpoint namespace for one executing agent.

    Managed agent instances are isolated by their concrete instance id.
    SDK-defined agents fall back to their stable agent id.

    LangGraph resets `checkpoint_ns` to `""` on every root-graph run
    (`pregel/_loop.py::PregelLoop.__init__`), so this namespace is carried by
    the graph agent's thread id instead (`graph_thread_id`).
    """
    return agent_instance_id or agent_id


async def load_checkpoint(
    checkpointer: AsyncCheckpointReader | None,
    *,
    thread_id: str,
    checkpoint_ns: str = "",
) -> tuple[Checkpoint, list[PendingWrite]] | None:
    """
    Load a thread's latest checkpoint together with its pending writes.

    Why pending_writes is returned alongside the checkpoint:
    - a LangGraph-native `interrupt()` leaves its only trace as a pending write
      on the fixed `"__interrupt__"` channel for the task that paused. Callers
      that need to tell "waiting on human input" apart from "turn is simply
      done" must inspect this list.
    """
    if checkpointer is None:
        return None
    checkpoint_tuple = await checkpointer.aget_tuple(
        checkpoint_config(
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
        )
    )
    if checkpoint_tuple is None:
        return None
    return checkpoint_tuple.checkpoint, list(checkpoint_tuple.pending_writes or [])
