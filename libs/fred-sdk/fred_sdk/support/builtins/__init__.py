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
Explicit package for the small native Fred built-in tool catalog.

Why this package exists:
- built-in tools are a tiny fixed catalog and should be visually separated from
  other support files
- this makes it easy to review exactly what Fred ships natively before any
  Python-authored tools or MCP/runtime tools are added

How to use it:
- import the `TOOL_REF_*` constants or the catalog lookup helpers from this
  package

Example:
- `from fred_sdk.support.builtins import TOOL_REF_KNOWLEDGE_SEARCH`
"""

from .catalog import (
    TOOL_REF_ARTIFACTS_PUBLISH_TEXT,
    TOOL_REF_GEO_RENDER_POINTS,
    TOOL_REF_KNOWLEDGE_SEARCH,
    TOOL_REF_RESOURCES_FETCH_TEXT,
    TOOL_REF_TRACES_SUMMARIZE_CONVERSATION,
    BuiltinToolBackend,
    BuiltinToolSpec,
    get_builtin_tool_spec,
    list_builtin_tool_specs,
)

__all__ = [
    "TOOL_REF_ARTIFACTS_PUBLISH_TEXT",
    "TOOL_REF_GEO_RENDER_POINTS",
    "TOOL_REF_KNOWLEDGE_SEARCH",
    "TOOL_REF_RESOURCES_FETCH_TEXT",
    "TOOL_REF_TRACES_SUMMARIZE_CONVERSATION",
    "BuiltinToolBackend",
    "BuiltinToolSpec",
    "get_builtin_tool_spec",
    "list_builtin_tool_specs",
]
