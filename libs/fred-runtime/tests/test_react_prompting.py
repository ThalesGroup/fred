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

from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)

from fred_runtime.react.react_prompting import build_attachment_context_suffix


def _binding(attachments_markdown: str | None) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(attachments_markdown=attachments_markdown),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


def test_attachment_context_suffix_announces_current_files() -> None:
    suffix = build_attachment_context_suffix(
        _binding(
            "## Attached files for this conversation\n"
            "- report.pdf: conversation document"
        )
    )

    assert "The user has attached one or more files" in suffix
    assert "scoped to the current conversation" in suffix
    assert "authorized access only" in suffix
    assert "Conversation documents may be available through document tools" in suffix
    assert "- report.pdf" in suffix


def test_attachment_context_suffix_is_absent_after_last_attachment_is_deleted() -> None:
    assert build_attachment_context_suffix(_binding(None)) == ""
    assert build_attachment_context_suffix(_binding("   ")) == ""


def test_attachment_context_suffix_drops_inline_image_data_urls() -> None:
    suffix = build_attachment_context_suffix(
        _binding(
            "## Attached files\n"
            "- diagram.png: conversation image (image/png, 250000 bytes)\n"
            "  data: data:image/png;base64,AAAA"
        )
    )

    assert "diagram.png" in suffix
    assert "metadata only" in suffix
    assert "250000 bytes" in suffix
    assert "data:image/png;base64" not in suffix
