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
The one check a Knowledge Base instance's configuration passes.

Used twice: when a team writes the configuration, and again before a pod is
handed it. Twice with the same code, because the two questions differ only in
when they are asked — a definition republished with different declared fields
leaves stored values that were valid when written and are not any more, and a
handler promised validated configuration must not be the one to discover it.

Strict on purpose. A `"500"` is not the integer 500: coercing it would mean the
value a team sees is not the value the handler receives, and every author would
have to defend against a platform that quietly rewrites their input.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from fred_sdk.contracts.models import FieldSpec, TuningValue

_TEXTUAL = frozenset({"string", "text", "text-multiline", "prompt", "secret", "url"})
_SCALARS = frozenset(_TEXTUAL | {"select", "boolean", "integer", "number"})


class InstanceConfigurationInvalid(Exception):
    """A submitted or stored configuration does not satisfy its declaration.

    Carries the offending field so a caller can point at it rather than at the
    form as a whole.
    """

    http_status = 422

    def __init__(self, message: str, *, field_key: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field_key = field_key


def _fail(key: str, detail: str) -> InstanceConfigurationInvalid:
    return InstanceConfigurationInvalid(f"{key}: {detail}", field_key=key)


def _check_scalar(key: str, field: FieldSpec, value: Any) -> None:
    kind = str(field.type)
    if kind in _TEXTUAL:
        if not isinstance(value, str):
            raise _fail(key, "must be a string")
        if field.pattern is not None and re.fullmatch(field.pattern, value) is None:
            raise _fail(key, f"must match {field.pattern!r}")
    elif kind == "select":
        if not isinstance(value, str):
            raise _fail(key, "must be a string")
        if field.enum is not None and value not in field.enum:
            raise _fail(key, f"must be one of {field.enum!r}")
    elif kind == "boolean":
        if not isinstance(value, bool):
            raise _fail(key, "must be a boolean")
    elif kind in ("integer", "number"):
        # `bool` is an `int` in Python, and True is not a quantity.
        if isinstance(value, bool):
            raise _fail(
                key, f"must be a{'n integer' if kind == 'integer' else ' number'}"
            )
        if kind == "integer" and not isinstance(value, int):
            raise _fail(key, "must be an integer")
        if kind == "number" and not isinstance(value, (int, float)):
            raise _fail(key, "must be a number")
        if field.min is not None and value < field.min:
            raise _fail(key, f"must be at least {field.min}")
        if field.max is not None and value > field.max:
            raise _fail(key, f"must be at most {field.max}")
    else:  # pragma: no cover - guarded by the caller
        raise _fail(key, f"has unsupported type {kind!r}")


def _check(key: str, field: FieldSpec, value: Any) -> None:
    kind = str(field.type)
    if kind == "array":
        if not isinstance(value, list):
            raise _fail(key, "must be an array")
        if field.item_type is None:
            raise _fail(key, "declares no item type, so its items cannot be checked")
        item_spec = field.model_copy(
            update={"type": field.item_type, "item_type": None}
        )
        if str(item_spec.type) not in _SCALARS:
            raise _fail(key, f"declares unsupported item type {field.item_type!r}")
        for item in value:
            _check_scalar(key, item_spec, item)
        return
    if kind == "object":
        if not isinstance(value, dict):
            raise _fail(key, "must be an object")
        for entry_key, entry in value.items():
            if not isinstance(entry_key, str):
                raise _fail(key, "must be keyed by strings")
            if not isinstance(entry, (str, int, float, bool)):
                raise _fail(key, "must hold scalar values only")
        return
    if kind not in _SCALARS:
        raise _fail(key, f"has unsupported type {kind!r}")
    _check_scalar(key, field, value)


def validate_instance_configuration(
    declared: list[FieldSpec], submitted: Mapping[str, Any]
) -> dict[str, TuningValue]:
    """Return the declared values, unchanged, or say which field is wrong.

    Unknown keys are refused rather than dropped: a team that misspells a key
    would otherwise watch its value vanish and the handler run without it.

    A declared default fills a field the submission omits, so what the handler
    receives is complete — but nothing is coerced, converted or reformatted.
    """
    by_key = {field.key: field for field in declared}
    unknown = sorted(set(submitted) - set(by_key))
    if unknown:
        raise InstanceConfigurationInvalid(
            f"Unknown configuration field(s): {unknown!r}", field_key=unknown[0]
        )

    resolved: dict[str, TuningValue] = {}
    for key, field in by_key.items():
        value = submitted.get(key)
        if value is None:
            if field.default is not None:
                resolved[key] = field.default
                continue
            if field.required:
                raise _fail(key, "is required")
            continue
        _check(key, field, value)
        resolved[key] = value
    return resolved
