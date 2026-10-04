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
Scope classification of capability settings: scope-private, public, asset key.

An agent lives in a scope (today a team or a personal space). A scope-private
setting points to an item owned by that scope and is reset when the agent is
copied to another scope; an asset key names a configuration file, recreated in
the destination; every other setting is public and travels as is.
Full rationale: docs/swift/capabilities/AUTHORING.md, "Scope-private settings".

How to use:
- typed models: `library_tag_ids: ScopePrivate[list[str]] = []`,
  `template_key: Annotated[str, AssetKey("template")] = "t.pptx"`, and
  `Public[...]` for an identifier-like field that is safe to copy
- catalog-declared fields (MCP servers): `FieldSpec.scope_private`
"""

from __future__ import annotations

import copy
import re
import types
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, TypeVar, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from ..models import FieldSpec

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class _ScopePrivateMarker:
    pass


@dataclass(frozen=True, slots=True)
class _PublicMarker:
    pass


@dataclass(frozen=True, slots=True)
class AssetKey:
    """Marks a field holding the key of a configuration file of `slot`."""

    slot: str


ScopePrivate = Annotated[T, _ScopePrivateMarker()]
Public = Annotated[T, _PublicMarker()]

# Identifier-like names: the guard requires these string fields to be classified.
_REFERENCE_NAME = re.compile(
    r"(^|_)(id|ids|uid|uids|key|keys|folder|folders|library|libraries|tag|tags|path|paths)$"
)


def _has(info: FieldInfo, marker_type: type) -> bool:
    return any(isinstance(item, marker_type) for item in info.metadata)


def _asset_slot(info: FieldInfo) -> str | None:
    for item in info.metadata:
        if isinstance(item, AssetKey):
            return item.slot
    return None


def _reset_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return reset_scope_private(value)
    if isinstance(value, list):
        return [_reset_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_reset_value(item) for item in value)
    if isinstance(value, dict):
        return {key: _reset_value(item) for key, item in value.items()}
    return value


def reset_scope_private(model: M, *, field_specs: Sequence[FieldSpec] = ()) -> M:
    """
    Return a copy of `model` with every scope-private field back to its default,
    at any depth. `field_specs` covers catalog-declared keys (MCP servers),
    which live as extra keys of an open model.
    """

    updates: dict[str, Any] = {}
    for name, info in type(model).model_fields.items():
        if _has(info, _ScopePrivateMarker):
            updates[name] = info.get_default(call_default_factory=True)
        else:
            updates[name] = _reset_value(getattr(model, name))
    reset = model.model_copy(update=updates)
    extra = reset.__pydantic_extra__
    if extra is not None:
        for spec in field_specs:
            if spec.scope_private and spec.key in extra:
                extra[spec.key] = copy.deepcopy(spec.default)
    return reset


def _walk_assets(value: Any) -> Iterator[tuple[str, str]]:
    if isinstance(value, BaseModel):
        for name, info in type(value).model_fields.items():
            field_value = getattr(value, name)
            slot = _asset_slot(info)
            if slot is None:
                yield from _walk_assets(field_value)
            elif isinstance(field_value, str) and field_value:
                yield slot, field_value
            elif isinstance(field_value, (list, tuple)):
                yield from ((slot, key) for key in field_value if key)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_assets(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_assets(item)


def asset_keys(model: BaseModel) -> dict[str, list[str]]:
    """The configuration-file keys a stored config holds, grouped by slot."""

    keys: dict[str, list[str]] = {}
    for slot, key in _walk_assets(model):
        keys.setdefault(slot, []).append(key)
    return keys


def _is_text(annotation: Any) -> bool:
    if annotation is str:
        return True
    origin = get_origin(annotation)
    if origin is Annotated:
        return _is_text(get_args(annotation)[0])
    if origin in (Union, types.UnionType):
        return any(
            _is_text(arg) for arg in get_args(annotation) if arg is not type(None)
        )
    if origin in (list, tuple, set, frozenset, Sequence):
        return any(_is_text(arg) for arg in get_args(annotation) if arg is not Ellipsis)
    return False


def _nested_models(annotation: Any) -> Iterator[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        yield annotation
        return
    for arg in get_args(annotation):
        yield from _nested_models(arg)


def unclassified_reference_fields(model_type: type[BaseModel]) -> list[str]:
    """
    Dotted paths of identifier-like text fields declared neither scope-private,
    public nor asset key. The capability guard test fails on any result.
    """

    found: list[str] = []
    seen: set[type[BaseModel]] = set()

    def visit(current: type[BaseModel], prefix: str) -> None:
        if current in seen:
            return
        seen.add(current)
        for name, info in current.model_fields.items():
            path = f"{prefix}{name}"
            classified = (
                _has(info, _ScopePrivateMarker)
                or _has(info, _PublicMarker)
                or _asset_slot(info) is not None
            )
            if (
                not classified
                and _REFERENCE_NAME.search(name)
                and _is_text(info.annotation)
            ):
                found.append(path)
            for nested in _nested_models(info.annotation):
                visit(nested, f"{path}.")

    visit(model_type, "")
    return found


def unclassified_reference_specs(field_specs: Sequence[FieldSpec]) -> list[str]:
    """Same check for catalog-declared fields, which classify via `scope_private`."""

    return [
        spec.key
        for spec in field_specs
        if spec.scope_private is None
        and _REFERENCE_NAME.search(spec.key.rsplit(".", 1)[-1])
        and (
            spec.type == "string"
            or (spec.type == "array" and spec.item_type == "string")
        )
    ]
