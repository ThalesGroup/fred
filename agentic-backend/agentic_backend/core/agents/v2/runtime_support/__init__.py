"""
Shared runtime plumbing for Fred v2 executors.

Why this package is intentionally lazy:
- graph, ReAct, and session plumbing may import checkpoint helpers during module
  initialization
- eager imports here would recreate circular dependencies between runtime
  families and session adaptation

How to use it:
- import `V2SessionAgent`, `FredSqlCheckpointer`, or checkpoint helper types
  from this package when wiring runtimes into chat/session or durable
  checkpoint flows

Example:
- `from agentic_backend.core.agents.v2.runtime_support import V2SessionAgent`
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from .checkpoints import (
        AsyncCheckpointReader,
        AsyncCheckpointWriter,
        CheckpointTupleLike,
        checkpoint_config,
        load_checkpoint,
    )
    from .session_agent import V2SessionAgent
    from .sql_checkpointer import FredSqlCheckpointer

__all__ = [
    "AsyncCheckpointReader",
    "AsyncCheckpointWriter",
    "CheckpointTupleLike",
    "FredSqlCheckpointer",
    "V2SessionAgent",
    "checkpoint_config",
    "load_checkpoint",
]

_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "AsyncCheckpointReader": ("checkpoints", "AsyncCheckpointReader"),
    "AsyncCheckpointWriter": ("checkpoints", "AsyncCheckpointWriter"),
    "CheckpointTupleLike": ("checkpoints", "CheckpointTupleLike"),
    "checkpoint_config": ("checkpoints", "checkpoint_config"),
    "load_checkpoint": ("checkpoints", "load_checkpoint"),
    "FredSqlCheckpointer": ("sql_checkpointer", "FredSqlCheckpointer"),
    "V2SessionAgent": ("session_agent", "V2SessionAgent"),
}


def __getattr__(name: str) -> object:
    export = _EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = export
    module = import_module(f"{__name__}.{module_name}")
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
