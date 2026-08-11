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


def resolved_token_usage(response: BaseMessage) -> tuple[int | None, int | None]:
    """`(input_tokens, cache_read_tokens)` off one LangChain response (CACHE-01).

    Reads `usage_metadata` directly — the same standardized LangChain shape
    (`input_token_details.cache_read`) fred-runtime's `normalize_token_usage`
    reads — kept as a local, dependency-free read (see module docstring)
    rather than importing fred-runtime's helper.
    """

    usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, dict):
        return (None, None)
    input_tokens = usage.get("input_tokens")
    details = usage.get("input_token_details")
    cache_read = details.get("cache_read") if isinstance(details, dict) else None
    return (
        input_tokens if isinstance(input_tokens, int) else None,
        cache_read if isinstance(cache_read, int) else None,
    )
