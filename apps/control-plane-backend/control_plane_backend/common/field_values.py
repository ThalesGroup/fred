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
The one check submitted values pass against a list of declared fields.

Three write paths do it — Knowledge Base instance configuration, per-team
capability settings, managed-agent tuning values — against two field-spec
models that are structural clones of each other. Duck-typed rather than
typed on either model, so neither subsystem has to import the other's; and
the exception is the caller's, so each route keeps its own status and
wording.

Strict on purpose: a `"500"` is not the integer 500. Coercing it would mean
the value an author sees is not the value the handler receives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Protocol

_TEXTUAL = frozenset({"string", "text", "text-multiline", "prompt", "secret", "url"})
_SCALARS = frozenset(_TEXTUAL | {"select", "boolean", "integer", "number"})

#: Builds the exception one bad field raises, from its key and what is wrong.
Fail = Callable[[str, str], Exception]


class FieldSpecLike(Protocol):
    """What a declared field has to expose to be validated.

    Read-only members on purpose: `fred_sdk`'s `FieldSpec` and control-plane's
    `ManagedAgentFieldSpec` both satisfy it as they are, no conversion.
    """

    @property
    def key(self) -> str: ...

    @property
    def type(self) -> str: ...

    @property
    def required(self) -> bool: ...

    @property
    def default(self) -> Any: ...

    @property
    def enum(self) -> list[str] | None: ...

    @property
    def min(self) -> float | None: ...

    @property
    def max(self) -> float | None: ...

    @property
    def pattern(self) -> str | None: ...

    @property
    def item_type(self) -> str | None: ...


@dataclass(frozen=True)
class _ItemSpec:
    """One array item seen as a field of its own.

    Carries the members an item is never checked against too, so that it
    satisfies `FieldSpecLike` and the same scalar check serves both.
    """

    key: str
    type: str
    required: bool = False
    default: Any = None
    enum: list[str] | None = None
    min: float | None = None
    max: float | None = None
    pattern: str | None = None
    item_type: str | None = None


@dataclass(frozen=True)
class _Checker:
    fail: Fail
    enum_on_every_type: bool
    strict_array_items: bool
    text_check: Callable[[str], str | None] | None

    def check(self, key: str, spec: FieldSpecLike, value: Any) -> None:
        kind = str(spec.type)
        if kind == "array":
            self._array(key, spec, value)
        elif kind == "object":
            self._object(key, value)
        elif kind in _SCALARS:
            self._scalar(key, spec, value, text_check=self.text_check)
        else:
            raise self.fail(key, f"has unsupported type {kind!r}")
        if self.enum_on_every_type and spec.enum is not None and value not in spec.enum:
            raise self.fail(key, f"must be one of {spec.enum!r}")

    def _scalar(
        self,
        key: str,
        spec: FieldSpecLike,
        value: Any,
        *,
        text_check: Callable[[str], str | None] | None,
    ) -> None:
        kind = str(spec.type)
        if kind in _TEXTUAL:
            if not isinstance(value, str):
                raise self.fail(key, "must be a string")
            if spec.pattern is not None and re.fullmatch(spec.pattern, value) is None:
                raise self.fail(key, f"must match {spec.pattern!r}")
            if text_check is not None:
                refused = text_check(value)
                if refused is not None:
                    raise self.fail(key, refused)
        elif kind == "select":
            if not isinstance(value, str):
                raise self.fail(key, "must be a string")
            if spec.enum is not None and value not in spec.enum:
                raise self.fail(key, f"must be one of {spec.enum!r}")
        elif kind == "boolean":
            if not isinstance(value, bool):
                raise self.fail(key, "must be a boolean")
        elif kind in ("integer", "number"):
            # `bool` is an `int` in Python, and True is not a quantity.
            if isinstance(value, bool):
                raise self.fail(
                    key, f"must be a{'n integer' if kind == 'integer' else ' number'}"
                )
            if kind == "integer" and not isinstance(value, int):
                raise self.fail(key, "must be an integer")
            if kind == "number" and not isinstance(value, (int, float)):
                raise self.fail(key, "must be a number")
            if spec.min is not None and value < spec.min:
                raise self.fail(key, f"must be at least {spec.min}")
            if spec.max is not None and value > spec.max:
                raise self.fail(key, f"must be at most {spec.max}")
        else:  # pragma: no cover - guarded by the caller
            raise self.fail(key, f"has unsupported type {kind!r}")

    def _array(self, key: str, spec: FieldSpecLike, value: Any) -> None:
        if not isinstance(value, list):
            raise self.fail(key, "must be an array")
        items: list[Any] = value
        if not self.strict_array_items:
            for item in items:
                self._loose_item(key, spec.item_type, item)
            return
        if spec.item_type is None:
            raise self.fail(
                key, "declares no item type, so its items cannot be checked"
            )
        if str(spec.item_type) not in _SCALARS:
            raise self.fail(key, f"declares unsupported item type {spec.item_type!r}")
        # Strict items answer to the field's own pattern and bounds, so an
        # array of URLs is checked the way a single URL would be.
        item_spec = _ItemSpec(
            key=key,
            type=str(spec.item_type),
            enum=spec.enum,
            min=spec.min,
            max=spec.max,
            pattern=spec.pattern,
        )
        for item in items:
            self._scalar(key, item_spec, item, text_check=None)

    def _loose_item(self, key: str, item_type: str | None, value: Any) -> None:
        # Type-checked only, and an undeclared item type accepts any scalar —
        # the declaration is never read when there is no item to read it for.
        if item_type is None:
            if not isinstance(value, (str, int, float, bool)):
                raise self.fail(key, "must hold scalar values only")
            return
        if str(item_type) not in _SCALARS:
            raise self.fail(key, f"declares unsupported item type {item_type!r}")
        self._scalar(
            key, _ItemSpec(key=key, type=str(item_type)), value, text_check=None
        )

    def _object(self, key: str, value: Any) -> None:
        if not isinstance(value, dict):
            raise self.fail(key, "must be an object")
        entries: dict[Any, Any] = value
        for entry_key, entry in entries.items():
            if not isinstance(entry_key, str):
                raise self.fail(key, "must be keyed by strings")
            if not isinstance(entry, (str, int, float, bool)):
                raise self.fail(key, "must hold scalar values only")


def validate_field_values(
    declared: Iterable[FieldSpecLike],
    submitted: Mapping[str, Any],
    *,
    fail: Fail,
    fail_unknown: Callable[[list[str]], Exception] | None = None,
    enforce_required: bool = True,
    fill_defaults: bool = False,
    enum_on_every_type: bool = False,
    strict_array_items: bool = True,
    text_check: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """Return the declared values, unchanged, or say which field is wrong.

    Nothing is coerced, converted or reformatted. What each caller decides:

    - `fail` / `fail_unknown`: the exception raised, hence the HTTP status and
      the wording. `fail_unknown=None` tolerates unknown keys and drops them,
      instead of refusing the whole submission.
    - `enforce_required`: refuse a declared-required field the submission
      omits (or sends as null).
    - `fill_defaults`: a declared default fills an omitted field, so what the
      handler receives is complete. Validated like any other value — a badly
      typed default would otherwise be the one value reaching a handler
      unchecked.
    - `enum_on_every_type`: check `enum` on every type, not on `select` alone.
    - `strict_array_items`: require a declared `item_type` and hold each item
      to the field's constraints, rather than type-checking items only.
    - `text_check`: an extra refusal on textual values, returning what is
      wrong with one, or `None` to accept it.
    """

    by_key = {spec.key: spec for spec in declared}
    if fail_unknown is not None:
        unknown = [key for key in submitted if key not in by_key]
        if unknown:
            raise fail_unknown(unknown)

    checker = _Checker(
        fail=fail,
        enum_on_every_type=enum_on_every_type,
        strict_array_items=strict_array_items,
        text_check=text_check,
    )
    resolved: dict[str, Any] = {}
    for key, spec in by_key.items():
        value = submitted.get(key)
        if value is None:
            if fill_defaults and spec.default is not None:
                checker.check(key, spec, spec.default)
                resolved[key] = spec.default
                continue
            if enforce_required and spec.required:
                raise fail(key, "is required")
            continue
        checker.check(key, spec, value)
        resolved[key] = value
    return resolved
