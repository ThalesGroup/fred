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

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata


class CheckpointTupleLike(Protocol):
    checkpoint: Checkpoint


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


def checkpoint_config(
    *, thread_id: str, checkpoint_id: str | None = None, checkpoint_ns: str = ""
) -> RunnableConfig:
    configurable: dict[str, object] = {
        "thread_id": thread_id,
        "checkpoint_ns": checkpoint_ns,
    }
    if checkpoint_id is not None:
        configurable["checkpoint_id"] = checkpoint_id
    return cast(RunnableConfig, {"configurable": configurable})


async def load_checkpoint(
    checkpointer: AsyncCheckpointReader | None,
    *,
    thread_id: str,
    checkpoint_id: str | None = None,
    checkpoint_ns: str = "",
) -> Checkpoint | None:
    if checkpointer is None:
        return None
    checkpoint_tuple = await checkpointer.aget_tuple(
        checkpoint_config(
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
            checkpoint_ns=checkpoint_ns,
        )
    )
    if checkpoint_tuple is None:
        return None
    return checkpoint_tuple.checkpoint
