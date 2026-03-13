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

from agentic_backend.agents.v2.definition_refs import class_path_for_definition_ref
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
    definition_ref: None = None


@dataclass(frozen=True, slots=True)
class ResolvedV2AgentClass:
    class_path: str
    implementation_kind: Literal[AgentImplementationKind.V2_DEFINITION]
    cls: type[AgentDefinition]
    definition_ref: str | None = None


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


def resolve_agent_reference(
    *,
    class_path: str | None,
    definition_ref: str | None,
) -> ResolvedAgentClass:
    """
    Resolve one agent target from either legacy class_path or v2 definition_ref.

    Resolution order:
    1. `definition_ref` (v2 stable id)
    2. `class_path` (legacy / compatibility path)
    """
    normalized_ref = definition_ref.strip() if isinstance(definition_ref, str) else None
    normalized_class_path = class_path.strip() if isinstance(class_path, str) else None

    if normalized_ref:
        if normalized_class_path:
            raise ValueError("Provide either definition_ref or class_path, not both.")
        mapped_class_path = class_path_for_definition_ref(normalized_ref)
        resolved = resolve_agent_class(mapped_class_path)
        if resolved.implementation_kind != AgentImplementationKind.V2_DEFINITION:
            raise TypeError(
                f"definition_ref '{normalized_ref}' does not target a v2 definition."
            )
        return ResolvedV2AgentClass(
            class_path=resolved.class_path,
            definition_ref=normalized_ref,
            implementation_kind=resolved.implementation_kind,
            cls=resolved.cls,
        )

    if normalized_class_path:
        return resolve_agent_class(normalized_class_path)

    raise ValueError("Either definition_ref or class_path must be provided.")
