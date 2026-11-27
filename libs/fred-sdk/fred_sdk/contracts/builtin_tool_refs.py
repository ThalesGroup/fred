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

"""Canonical Fred-owned names and exact aliases accepted from older callers."""

TOOL_REF_KNOWLEDGE_SEARCH = "knowledge_search"
TOOL_REF_SIMILARITY_SEARCH = "knowledge_similarity_search"
TOOL_REF_TRACES_SUMMARIZE_CONVERSATION = "traces_summarize_conversation"
TOOL_REF_GEO_RENDER_POINTS = "geo_render_points"
TOOL_REF_CHART_RENDER = "chart_render"

TOOL_REF_ASK_USER = "platform_ask_user"
TOOL_REF_LOAD_SKILL = "platform_load_skill"
TOOL_REF_READ_SKILL_FILE = "platform_read_skill_file"

_LEGACY_NAMES = {
    TOOL_REF_KNOWLEDGE_SEARCH: "knowledge.search",
    TOOL_REF_SIMILARITY_SEARCH: "knowledge.similarity_search",
    TOOL_REF_TRACES_SUMMARIZE_CONVERSATION: "traces.summarize_conversation",
    TOOL_REF_GEO_RENDER_POINTS: "geo.render_points",
    TOOL_REF_CHART_RENDER: "chart.render",
}
_CANONICAL_NAMES = {legacy: canonical for canonical, legacy in _LEGACY_NAMES.items()}


def canonical_builtin_tool_ref(tool_ref: str) -> str:
    """Resolve an old Fred-owned reference, preserving other identifiers verbatim."""
    return _CANONICAL_NAMES.get(tool_ref, tool_ref)


def legacy_builtin_tool_ref(tool_ref: str) -> str | None:
    """Find the previous name when checking an existing exact-name approval policy."""
    return _LEGACY_NAMES.get(tool_ref)
