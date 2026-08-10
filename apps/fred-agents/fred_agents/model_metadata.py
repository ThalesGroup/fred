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
Shared helper for reading back which model actually answered a LangChain
call, off `response_metadata` — deliberately dependency-free (no
fred-runtime import): `model_name`/`model` are the same two keys any
provider-agnostic caller would read, so this has no reason to depend on
fred-runtime internals. Lives at the app root rather than inside a specific
capability package (`routing_probe`, `test_assistant`, ...) since those are
meant to stay independent of one another.
"""

from __future__ import annotations

from langchain_core.messages import BaseMessage


def resolved_model_name(response: BaseMessage) -> str | None:
    """The model name off one LangChain response, or None if absent/unreadable."""

    metadata = getattr(response, "response_metadata", None)
    if not isinstance(metadata, dict):
        return None
    name = metadata.get("model_name") or metadata.get("model")
    return name if isinstance(name, str) and name.strip() else None
