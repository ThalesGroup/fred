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

"""Helpers for accessing the canonical OpenFGA schema."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_SCHEMA_JSON_PATH = Path(__file__).with_name("schema.fga.json")


@lru_cache(maxsize=1)
def _load_default_schema_json_source() -> str:
    """Read and cache the JSON form of the OpenFGA schema."""

    return _SCHEMA_JSON_PATH.read_text(encoding="utf-8")


DEFAULT_SCHEMA = _load_default_schema_json_source()
