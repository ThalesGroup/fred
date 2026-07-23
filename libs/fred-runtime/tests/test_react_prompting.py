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

from types import SimpleNamespace
from typing import cast

from fred_runtime.react.react_prompting import (
    build_attachment_context_suffix,
    build_context_prompt_suffix,
    build_global_base_prompt_suffix,
    build_tool_failure_recovery_suffix,
    compose_system_prompt,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import ReActAgentDefinition
from fred_sdk.resources.prompts import GLOBAL_BASE_PROMPT_MARKDOWN

_EXPECTED_MERMAID_FRAGMENT = "When you include Mermaid diagrams, follow these rules strictly so the diagram always parses:"


def _binding(
    attachments_markdown: str | None = None,
    *,
    context_prompt_text: str | None = None,
    language: str | None = None,
) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            attachments_markdown=attachments_markdown,
            context_prompt_text=context_prompt_text,
            language=language,
        ),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


def _definition() -> ReActAgentDefinition:
    # ``compose_system_prompt`` only reads ``definition.policy().guardrails`` via
    # ``build_guardrail_suffix``; a minimal stand-in keeps these tests focused on
    # composition and ordering. Guardrail rendering is exercised elsewhere.
    return cast(
        ReActAgentDefinition,
        SimpleNamespace(policy=lambda: SimpleNamespace(guardrails=[])),
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


def test_tool_failure_recovery_suffix_tells_model_not_to_surface_raw_errors() -> None:
    # Regression for #2073: some capability tools catch their own exceptions and
    # return a troubleshooting message as an ordinary tool result. Without this
    # guidance the model has surfaced that raw text as its final answer instead
    # of retrying or falling back to context already gathered.
    suffix = build_tool_failure_recovery_suffix()

    assert "never present that raw text as your final answer" in suffix
    assert "retry the call with corrected arguments" in suffix
    assert "answer from what other calls have already returned" in suffix
    # Composed onto the end of the system prompt, so it must self-separate.
    assert suffix.startswith("\n\n")


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


def test_context_prompt_suffix_injects_selected_prompt_text() -> None:
    # #1915: the control plane resolves a session's selected prompts into
    # runtime_context.context_prompt_text; the runtime must fold that into the
    # system prompt, or the selection ("speak Spanish") never reaches the model.
    suffix = build_context_prompt_suffix(
        _binding(context_prompt_text="Always respond in Spanish."),
        agent_id="agent-1",
    )

    assert "Always respond in Spanish." in suffix
    # Composed onto the end of the system prompt, so it must self-separate.
    assert suffix.startswith("\n\n")


def test_context_prompt_suffix_is_absent_without_a_selection() -> None:
    assert build_context_prompt_suffix(_binding(), agent_id="agent-1") == ""
    assert (
        build_context_prompt_suffix(
            _binding(context_prompt_text="   "), agent_id="agent-1"
        )
        == ""
    )


def test_context_prompt_suffix_renders_safe_tokens() -> None:
    # A library prompt may use the same validated tokens as an agent template,
    # so it goes through the safe renderer rather than being appended verbatim.
    suffix = build_context_prompt_suffix(
        _binding(
            context_prompt_text="Reply in {response_language}.",
            language="fr",
        ),
        agent_id="agent-1",
    )

    assert "Reply in français." in suffix
    assert "{response_language}" not in suffix


def test_compose_system_prompt_folds_selected_prompt_and_attachment() -> None:
    # Both ReAct and Deep delegate to this composer, so this single test locks
    # the #1915 fix and the previously-missing Deep attachment suffix at once.
    prompt = compose_system_prompt(
        "BASE-TEMPLATE",
        binding=_binding(
            "## Attached files\n- report.pdf: conversation document",
            context_prompt_text="Always respond in Spanish.",
        ),
        definition=_definition(),
        agent_id="agent-1",
        tool_suffix="\n\nTOOL-SUFFIX",
    )

    assert prompt.startswith("BASE-TEMPLATE")
    assert "TOOL-SUFFIX" in prompt
    assert "Always respond in Spanish." in prompt
    assert "- report.pdf" in prompt
    assert "never present that raw text as your final answer" in prompt
    # Ordering: the global-base output contract and the tool-failure recovery
    # notice (both hard invariants) precede the per-turn user context, and the
    # selected prompt precedes the (freshest) attachment block.
    assert prompt.index(_EXPECTED_MERMAID_FRAGMENT) < prompt.index(
        "never present that raw text as your final answer"
    )
    assert prompt.index(
        "never present that raw text as your final answer"
    ) < prompt.index("Always respond in Spanish.")
    assert prompt.index("Always respond in Spanish.") < prompt.index("- report.pdf")


def test_compose_system_prompt_places_runtime_suffixes_before_user_context() -> None:
    # Runtime-specific notices (e.g. the Deep filesystem suffix) belong with the
    # system invariants, ahead of the selected chat-context prompt.
    prompt = compose_system_prompt(
        "BASE-TEMPLATE",
        binding=_binding(context_prompt_text="Speak Spanish."),
        definition=_definition(),
        agent_id="agent-1",
        runtime_suffixes=("\n\nFILESYSTEM-NOTICE",),
    )

    assert "FILESYSTEM-NOTICE" in prompt
    assert prompt.index("FILESYSTEM-NOTICE") < prompt.index("Speak Spanish.")
