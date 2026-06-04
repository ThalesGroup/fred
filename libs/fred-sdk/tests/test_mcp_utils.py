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
Offline unit tests for fred_sdk.support.mcp_utils.normalize_mcp_content.

All branches:
- string passthrough
- list of text blocks → joined string
- content_and_artifact tuple
- list with mixed / non-text blocks
- non-string, non-list fallback
"""

from __future__ import annotations

from fred_sdk.support.mcp_utils import normalize_mcp_content


class TestNormalizeMcpContent:
    def test_string_passthrough(self) -> None:
        assert normalize_mcp_content("already a string") == "already a string"

    def test_empty_string_passthrough(self) -> None:
        assert normalize_mcp_content("") == ""

    def test_single_text_block(self) -> None:
        content = [{"type": "text", "text": "hello"}]
        assert normalize_mcp_content(content) == "hello"

    def test_multiple_text_blocks_joined_with_newline(self) -> None:
        content = [
            {"type": "text", "text": "line one"},
            {"type": "text", "text": "line two"},
        ]
        assert normalize_mcp_content(content) == "line one\nline two"

    def test_non_text_blocks_skipped(self) -> None:
        content = [
            {"type": "image", "url": "https://img"},
            {"type": "text", "text": "kept"},
        ]
        assert normalize_mcp_content(content) == "kept"

    def test_blocks_without_text_key_skipped(self) -> None:
        content = [{"type": "text"}, {"type": "text", "text": "present"}]
        assert normalize_mcp_content(content) == "present"

    def test_empty_list_falls_through_to_original(self) -> None:
        assert normalize_mcp_content([]) == []

    def test_list_with_no_text_blocks_falls_through(self) -> None:
        content = [{"type": "image"}]
        assert normalize_mcp_content(content) == content

    def test_content_and_artifact_tuple_normalizes_content_part(self) -> None:
        artifact = {"some": "data"}
        content_part = [{"type": "text", "text": "extracted"}]
        result = normalize_mcp_content((content_part, artifact))
        assert result == ("extracted", artifact)

    def test_content_and_artifact_tuple_string_content_passthrough(self) -> None:
        artifact = [1, 2, 3]
        result = normalize_mcp_content(("already string", artifact))
        assert result == ("already string", artifact)

    def test_non_string_non_list_returned_unchanged(self) -> None:
        assert normalize_mcp_content(42) == 42
        assert normalize_mcp_content(None) is None
        assert normalize_mcp_content({"key": "val"}) == {"key": "val"}
