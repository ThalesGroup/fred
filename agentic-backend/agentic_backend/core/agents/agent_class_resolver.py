"""
Shared class-resolution helpers for Fred agent implementations.

Why this file exists:
- The platform now has two authoring models during the transition:
  legacy `AgentFlow` classes and new v2 `AgentDefinition` classes.
- Service, loader, controller, and factory code all need the same resolution
  logic; keeping it in one file avoids silent semantic drift.
- The helper stays intentionally small: it only answers "what kind of agent
  class is this?" and "can Fred instantiate it?".
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from enum import Enum
from typing import Literal, TypeAlias

from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.v2.models import AgentDefinition


class AgentImplementationKind(str, Enum):
    FLOW = "flow"
    V2_DEFINITION = "v2_definition"


@dataclass(frozen=True, slots=True)
class ResolvedFlowAgentClass:
    class_path: str
    implementation_kind: Literal[AgentImplementationKind.FLOW]
    cls: type[AgentFlow]


@dataclass(frozen=True, slots=True)
class ResolvedV2AgentClass:
    class_path: str
    implementation_kind: Literal[AgentImplementationKind.V2_DEFINITION]
    cls: type[AgentDefinition]


ResolvedAgentClass: TypeAlias = ResolvedFlowAgentClass | ResolvedV2AgentClass


def resolve_agent_class(class_path: str) -> ResolvedAgentClass:
    module_name, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)

    if not isinstance(cls, type):
        raise TypeError(f"Resolved object for {class_path!r} is not a class.")

    if issubclass(cls, AgentFlow):
        return ResolvedFlowAgentClass(
            class_path=class_path,
            implementation_kind=AgentImplementationKind.FLOW,
            cls=cls,
        )

    if issubclass(cls, AgentDefinition):
        return ResolvedV2AgentClass(
            class_path=class_path,
            implementation_kind=AgentImplementationKind.V2_DEFINITION,
            cls=cls,
        )

    raise TypeError(
        f"Class '{class_name}' must inherit from AgentFlow or AgentDefinition."
    )
