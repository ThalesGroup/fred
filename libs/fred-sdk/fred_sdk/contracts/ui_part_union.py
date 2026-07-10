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
`UiPart` union registration — capability chat parts join the union at
model-build time (#1977, RFC AGENT-CAPABILITY-RFC §3.6/§4).

Why this module exists:
- `UiPart` (`fred_sdk/contracts/context.py`) was a hand-edited hotspot: adding
  a chat part meant editing the union literal plus every place that switches
  on part kinds. Capabilities declare `manifest.chat_parts` instead; this
  module folds those classes into the ONE union so every referencing model
  (runtime events, tool results, OpenAI-compat metadata) and the generated
  OpenAPI pick them up with zero hand edits.

How it works (and why it is this involved):
- pydantic resolves field annotations at class creation, so swapping the
  module-level `UiPart` alias alone changes nothing for already-built models.
  `rebuild_ui_part_union` therefore (1) swaps the alias in every loaded module
  that imported it, (2) rewrites the resolved annotation objects of every
  affected model field, and (3) force-rebuilds affected models leaves-first so
  embedding models (e.g. `FredChatCompletionChunk` → `FredChunkChoice` →
  `FredChunkMetadata`) re-capture the extended nested schemas.

How to use:
- boot / registration (the only intended caller is the capability registry):
  `rebuild_ui_part_union(registry.chat_parts())`
- always pass the FULL extra set: the result is `BASE_UI_PARTS + extra_parts`,
  never cumulative across calls — calling with `()` restores the frozen base
  union (tests rely on this to undo extension)
- validators needing the current union must resolve it lazily:
  `TypeAdapter(current_ui_part_union())` AFTER registration, never a
  module-level adapter built at import time
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from graphlib import TopologicalSorter
from typing import Annotated, Any, Union, get_args, get_origin

from pydantic import BaseModel, Field

from . import context as _context
from .context import GeoPart, LinkPart

BASE_UI_PARTS: tuple[type[BaseModel], ...] = (LinkPart, GeoPart)
"""The frozen union members every pod ships (RFC §3.6): link, geo."""


def current_ui_part_union() -> Any:
    """
    The `UiPart` union as currently registered (base + capability parts).

    Use this for validators built AFTER capability registration (e.g.
    `TypeAdapter(current_ui_part_union())`); a `from ... import UiPart` frozen
    at import time predates registration in scripts and long-lived modules.
    """

    return _context.UiPart


def rebuild_ui_part_union(extra_parts: Sequence[type[BaseModel]] = ()) -> None:
    """
    Rebuild the `UiPart` union as `BASE_UI_PARTS + extra_parts` and propagate
    it to every already-built pydantic model in the process.

    Notes:
    - deterministic, not cumulative: the union is always rebuilt from the
      frozen base plus exactly the given extras (duplicates dropped, order
      preserved); `rebuild_ui_part_union(())` restores the frozen contract
    - discriminator-collision checking is the capability registry's job
      (`DuplicateChatPartKindError` at boot); pydantic still fails here as a
      backstop if two members share a `type` value
    """

    old_alias = _context.UiPart
    members: list[type[BaseModel]] = list(BASE_UI_PARTS)
    for part in extra_parts:
        if part not in members:
            members.append(part)
    union = members[0] if len(members) == 1 else Union[tuple(members)]
    new_alias = Annotated[union, Field(discriminator="type")]

    _swap_module_globals(old_alias, new_alias)
    _rebuild_referencing_models(old_alias, new_alias)


# -- propagation machinery ----------------------------------------------------


def _swap_module_globals(old_alias: Any, new_alias: Any) -> None:
    """Point every loaded module's imported `UiPart` name at the new alias."""

    for module in list(sys.modules.values()):
        module_dict = getattr(module, "__dict__", None)
        if not module_dict:
            continue
        for name, value in list(module_dict.items()):
            if value is old_alias:
                module_dict[name] = new_alias


def _replace_in_annotation(annotation: Any, old_alias: Any, new_alias: Any) -> Any:
    """Return `annotation` with every occurrence of the old alias swapped."""

    if annotation is old_alias:
        return new_alias
    origin = get_origin(annotation)
    if origin is None:
        return annotation
    args = get_args(annotation)
    new_args = tuple(_replace_in_annotation(a, old_alias, new_alias) for a in args)
    if all(new is arg for new, arg in zip(new_args, args)):
        return annotation
    if origin is Union:
        return Union[new_args]
    if get_origin(Annotated[int, 0]) is origin:  # Annotated[...] wrapper
        return Annotated[new_args]
    return origin[new_args]


def _models_in_annotation(annotation: Any, acc: set[type[BaseModel]]) -> None:
    """Collect every pydantic model class referenced inside an annotation."""

    if isinstance(annotation, type):
        if issubclass(annotation, BaseModel):
            acc.add(annotation)
        return
    for arg in get_args(annotation):
        _models_in_annotation(arg, acc)


def _all_models() -> list[type[BaseModel]]:
    """Every pydantic model class defined in the process (subclass walk)."""

    seen: set[type[BaseModel]] = set()
    stack: list[type[BaseModel]] = [BaseModel]
    while stack:
        cls = stack.pop()
        for sub in cls.__subclasses__():
            if sub not in seen:
                seen.add(sub)
                stack.append(sub)
    return list(seen)


def _rebuild_referencing_models(old_alias: Any, new_alias: Any) -> None:
    """
    Rewrite resolved field annotations and force-rebuild affected models.

    Affected = models whose fields carry the old alias, plus (transitively)
    every model embedding an affected model — embedding models captured the
    nested core schema at build time and must re-capture it. Rebuild order is
    dependencies-first (topological), with one settling pass for cycles.
    """

    models = _all_models()

    # Pass 1 — swap the alias inside resolved annotations; seed the dirty set.
    dirty: set[type[BaseModel]] = set()
    field_models: dict[type[BaseModel], set[type[BaseModel]]] = {}
    for model in models:
        fields = getattr(model, "__pydantic_fields__", None)
        if not fields:
            continue
        referenced: set[type[BaseModel]] = set()
        for field in fields.values():
            replaced = _replace_in_annotation(field.annotation, old_alias, new_alias)
            if replaced is not field.annotation:
                field.annotation = replaced
                dirty.add(model)
            _models_in_annotation(field.annotation, referenced)
        field_models[model] = referenced

    # Pass 2 — propagate dirtiness to embedding models, to a fixpoint.
    changed = True
    while changed:
        changed = False
        for model, referenced in field_models.items():
            if model not in dirty and not referenced.isdisjoint(dirty):
                dirty.add(model)
                changed = True

    if not dirty:
        return

    # Pass 3 — rebuild dependencies-first so parents re-capture new child
    # schemas; a final settling pass covers reference cycles.
    graph = {
        model: {dep for dep in field_models[model] if dep in dirty and dep is not model}
        for model in dirty
    }
    try:
        ordered = list(TopologicalSorter(graph).static_order())
    except Exception:  # pragma: no cover - cyclic model references
        ordered = list(dirty) + list(dirty)
    for model in ordered:
        model.model_rebuild(force=True)
