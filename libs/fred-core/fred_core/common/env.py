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

from __future__ import annotations

import os
from typing import Any

"""
Central boolean parsing helpers for environment flags and loose runtime payloads.

Why this file exists:
- The same string checks (`"1"`, `"true"`, `"yes"`, `"on"`) were duplicated in
  multiple services.
- One shared helper keeps behavior consistent and removes repeated code.

How to use:
```python
from fred_core.common import read_env_bool, coerce_bool

docs_enabled = read_env_bool("PRODUCTION_FASTAPI_DOCS_ENABLED", default=True)
requires_approval = coerce_bool(payload.get("requires_approval"), default=False)
```
"""

_TRUTHY_STRINGS: frozenset[str] = frozenset({"1", "true", "yes", "on", "y"})
_FALSY_STRINGS: frozenset[str] = frozenset({"0", "false", "no", "off", "n"})


def coerce_bool(value: Any, default: bool = False) -> bool:
    """
    Convert common runtime inputs to bool.

    Supported input types:
    - `bool`: returned as-is
    - `int` / `float`: zero => False, non-zero => True
    - `str`: normalized and matched against known true/false tokens
    - anything else: fallback to `default`
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUTHY_STRINGS:
            return True
        if normalized in _FALSY_STRINGS:
            return False
    return default


def read_env_bool(name: str, default: bool) -> bool:
    """
    Read and parse a boolean environment variable.

    Use this for runtime flags loaded from environment variables.
    """
    return coerce_bool(os.getenv(name), default=default)
