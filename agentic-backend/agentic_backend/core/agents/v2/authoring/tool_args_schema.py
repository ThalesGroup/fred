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
Private schema helpers for Python-authored v2 tools.

Why this module exists:
- the public authoring API should not mix runtime registration with low-level
  schema generation details
- authored tools still need strict argument schemas derived from Python
  signatures and a structured-output schema variant compatible with the model
  adapter

How to use it:
- import these helpers only from `authoring/api.py`
- agent authors should not import this module directly

Example:
- `args_schema = build_args_schema(search_documents)`
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, cast, get_type_hints

from pydantic import BaseModel, create_model


def build_args_schema(fn: Callable[..., object]) -> type[BaseModel]:
    """
    Build a pydantic args schema from one authored tool function signature.

    Why this exists:
    - authored Python tools should feel like plain Python while still producing
      a strict runtime argument schema for validation and tool binding

    How to use it:
    - pass one function decorated later with `@tool(...)`
    - the first parameter is reserved for `ToolContext`; remaining parameters
      become schema fields

    Example:
    - `args_schema = build_args_schema(my_tool)`
    """
    tool_fn = cast(Callable[..., object], fn)
    signature = inspect.signature(tool_fn)
    parameters = list(signature.parameters.values())
    if not parameters:
        raise TypeError(
            f"Authored tool {getattr(tool_fn, '__name__', '<tool>')} must accept a first ToolContext parameter."
        )

    fields: dict[str, tuple[object, object]] = {}
    type_hints = get_type_hints(tool_fn, include_extras=True)
    for parameter in parameters[1:]:
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            raise TypeError(
                f"Authored tool {getattr(tool_fn, '__name__', '<tool>')} uses unsupported parameter kind for {parameter.name!r}."
            )
        annotation = type_hints.get(parameter.name, Any)
        default = (
            ... if parameter.default is inspect.Parameter.empty else parameter.default
        )
        fields[parameter.name] = (annotation, default)

    tool_name = getattr(tool_fn, "__name__", "AuthoredTool")
    model_name = "".join(part.capitalize() for part in tool_name.split("_")) + "Args"
    return create_model(model_name, **cast(dict[str, Any], fields))
