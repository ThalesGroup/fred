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
from fred_sdk.resources.prompts import GLOBAL_BASE_PROMPT_MARKDOWN

from fred_runtime.react.react_prompting import (
    build_attachment_context_suffix,
    build_global_base_prompt_suffix,
)

_EXPECTED_MERMAID_FRAGMENT = "When you include Mermaid diagrams, follow these rules strictly so the diagram always parses:"


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


def test_global_base_prompt_suffix_injects_mermaid_contract() -> None:
    suffix = build_global_base_prompt_suffix()

    # The shared renderer/output contract is appended at runtime, not baked into
    # the agent's editable system prompt.
    assert _EXPECTED_MERMAID_FRAGMENT in suffix
    assert GLOBAL_BASE_PROMPT_MARKDOWN in suffix


def test_global_base_prompt_suffix_starts_with_a_blank_separator() -> None:
    # Composed onto the end of the system prompt, so it must self-separate.
    assert build_global_base_prompt_suffix().startswith("\n\n")


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
    # Attachments (documents and images) are ingested and retrievable, and the
    # model is told to search them before answering — see issue #1852.
    assert "ingested and indexed for retrieval" in suffix
    assert "search tool" in suffix
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
    assert "250000 bytes" in suffix
    # The base64 payload is stripped, but the image is still presented as a
    # retrievable attachment the model must search — not as un-analyzable metadata.
    assert "data:image/png;base64" not in suffix
    assert "search tool" in suffix


def test_attachment_context_suffix_instructs_model_to_search_images() -> None:
    suffix = build_attachment_context_suffix(
        _binding(
            "## Attached files\n"
            "- diagram.png: conversation image (image/png, 250000 bytes)\n"
            "  data: data:image/png;base64,AAAA"
        )
    )

    # Regression for #1852: an attached image is vectorized/retrievable, so the
    # prompt must tell the model to retrieve it via the search tool rather than
    # imply it cannot analyze the image.
    assert "documents AND images" in suffix
    assert "MUST first call the search tool" in suffix
    assert "do not claim you cannot see or analyze an attachment" in suffix
