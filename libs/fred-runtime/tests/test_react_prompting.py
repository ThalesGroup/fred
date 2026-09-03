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

import pytest
from fred_runtime.capabilities.mcp import McpPromptGroup
from fred_runtime.react import react_prompting
from fred_runtime.react.react_prompting import (
    build_attachment_context_suffix,
    build_context_prompt_suffix,
    build_document_scope_suffix,
    build_global_base_prompt_suffix,
    build_platform_instructions_prefix,
    build_platform_prompt_prefix,
    compose_system_prompt,
)
from fred_runtime.react.react_tool_binding import (
    BoundTool,
    build_runtime_tool_prompt_suffix,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.resources.prompts import GLOBAL_BASE_PROMPT_MARKDOWN
from langchain_core.tools import BaseTool

_EXPECTED_MERMAID_FRAGMENT = "When you include Mermaid diagrams, follow these rules strictly so the diagram always parses:"


def _binding(
    attachments_markdown: str | None = None,
    *,
    context_prompt_text: str | None = None,
    language: str | None = None,
    platform_prompt: str | None = None,
    selected_document_uids: list[str] | None = None,
) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        platform_prompt=platform_prompt,
        runtime_context=RuntimeContext(
            attachments_markdown=attachments_markdown,
            context_prompt_text=context_prompt_text,
            language=language,
            selected_document_uids=selected_document_uids,
        ),
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


def test_tool_prompt_suffix_has_no_calling_rules_or_repetition_text() -> None:
    # The "Tool calling rules" block (generic hygiene lines + the anti-repetition
    # instruction) was removed: reasoning continuity now threads the model's own
    # reasoning within an open tool loop instead of stripping it
    # (`thread_reasoning_within_open_turn`, `RUNTIME-EXECUTION-CONTRACT.md` §8.37),
    # which is what the anti-repetition instruction existed to work around. Pin
    # the absence so it isn't silently reintroduced.
    suffix = build_runtime_tool_prompt_suffix(
        [
            BoundTool(
                runtime_name="search_documents",
                description="Search the corpus.",
                tool=cast(BaseTool, SimpleNamespace(name="search_documents")),
            )
        ]
    )

    assert "Tool calling rules" not in suffix
    assert "Never repeat a tool call" not in suffix


def test_tool_prompt_suffix_keeps_only_the_opening_paragraph() -> None:
    # #2412: the `tools` API parameter already carries the full description on
    # every call. Repeating it in the suffix duplicated it a second time, and
    # that duplicate scaled with tool count. Only the summary (what the tool
    # does, for orchestration) survives here — the full "how to use it" text
    # stays solely in the `tools` parameter.
    multi_line_description = "Locate a keyword across authorized tabular datasets.\n\nWhy this exists:\n- long explanation..."
    suffix = build_runtime_tool_prompt_suffix(
        [
            BoundTool(
                runtime_name="search_tabular_values",
                description=multi_line_description,
                tool=cast(BaseTool, SimpleNamespace(name="search_tabular_values")),
            )
        ]
    )

    assert (
        "- search_tabular_values: Locate a keyword across authorized tabular datasets."
        in suffix
    )
    assert "Why this exists" not in suffix
    assert "long explanation" not in suffix


def test_tool_prompt_suffix_keeps_a_hand_wrapped_opening_sentence_whole() -> None:
    # A summary sentence wrapped across two source lines (this repo's normal
    # docstring style, e.g. `search_documents_using_vectorization`) must not
    # be cut mid-sentence by the paragraph boundary — only a blank line ends
    # the summary, and internal newlines/indentation collapse to one space so
    # the rendered bullet stays on a single line.
    wrapped_description = (
        "Search the selected document libraries using semantic similarity\n"
        "            (RAG) — call this BEFORE answering any factual question.\n"
        "\n"
        "            Longer explanation that must not appear in the suffix."
    )
    suffix = build_runtime_tool_prompt_suffix(
        [
            BoundTool(
                runtime_name="search_documents_using_vectorization",
                description=wrapped_description,
                tool=cast(
                    BaseTool,
                    SimpleNamespace(name="search_documents_using_vectorization"),
                ),
            )
        ]
    )

    assert (
        "- search_documents_using_vectorization: Search the selected document "
        "libraries using semantic similarity (RAG) — call this BEFORE "
        "answering any factual question."
    ) in suffix
    assert "Longer explanation" not in suffix


def test_tool_prompt_suffix_handles_a_description_with_a_leading_blank_line() -> None:
    # A description authored as `"""\nSummary text.\n\nDetail..."""` opens
    # with a blank line before the real summary — a plausible triple-quoted
    # docstring or admin-authored manifest override. `.strip()` must recover
    # the summary instead of yielding an empty bullet.
    leading_blank_description = "\n  Summary text.\n\nDetail that must not appear."
    suffix = build_runtime_tool_prompt_suffix(
        [
            BoundTool(
                runtime_name="some_tool",
                description=leading_blank_description,
                tool=cast(BaseTool, SimpleNamespace(name="some_tool")),
            )
        ]
    )

    assert "- some_tool: Summary text." in suffix
    assert "- some_tool: \n" not in suffix
    assert "Detail that must not appear" not in suffix


def _grouped_tool(name: str, server_id: str) -> BoundTool:
    return BoundTool(
        runtime_name=name,
        description=f"Do {name} things.",
        tool=cast(BaseTool, SimpleNamespace(name=name)),
        mcp_server_id=server_id,
    )


def test_tool_prompt_suffix_groups_tools_by_mcp_server_with_a_title_header() -> None:
    # #2455: tools tagged with a server id that matches a given McpPromptGroup
    # render under that group's own "Tools for {title}:" header, not the flat
    # list.
    suffix = build_runtime_tool_prompt_suffix(
        [
            _grouped_tool("read_query", "mcp-tabular"),
            _grouped_tool("search_documents", "mcp-text"),
        ],
        mcp_prompt_groups=[
            McpPromptGroup(
                server_id="mcp-tabular", title="tabular action", agent_instructions=None
            ),
            McpPromptGroup(
                server_id="mcp-text", title="document search", agent_instructions=None
            ),
        ],
    )

    tabular_header = suffix.index("Tools for tabular action:")
    text_header = suffix.index("Tools for document search:")
    assert "- read_query:" in suffix[tabular_header:text_header]
    assert "- search_documents:" not in suffix[tabular_header:text_header]
    assert "- search_documents:" in suffix[text_header:]


def test_tool_prompt_suffix_inlines_agent_instructions_immediately_after_its_group() -> (
    None
):
    suffix = build_runtime_tool_prompt_suffix(
        [
            _grouped_tool("read_query", "mcp-tabular"),
            _grouped_tool("search_documents", "mcp-text"),
        ],
        mcp_prompt_groups=[
            McpPromptGroup(
                server_id="mcp-tabular",
                title="tabular action",
                agent_instructions="Follow this order before answering.",
            ),
            McpPromptGroup(
                server_id="mcp-text", title="document search", agent_instructions=None
            ),
        ],
    )

    header = suffix.index("Tools for tabular action:")
    instructions = suffix.index("Follow this order before answering.")
    next_header = suffix.index("Tools for document search:")
    assert header < instructions < next_header


def test_tool_prompt_suffix_skips_agent_instructions_block_when_none_declared() -> None:
    suffix = build_runtime_tool_prompt_suffix(
        [_grouped_tool("read_query", "mcp-tabular")],
        mcp_prompt_groups=[
            McpPromptGroup(
                server_id="mcp-tabular", title="tabular action", agent_instructions=None
            )
        ],
    )

    assert suffix.rstrip().endswith("- read_query: Do read_query things.")


def test_tool_prompt_suffix_places_ungrouped_tools_under_other_tools_when_a_group_is_present() -> (
    None
):
    suffix = build_runtime_tool_prompt_suffix(
        [
            BoundTool(
                runtime_name="local_tool",
                description="A native, non-MCP tool.",
                tool=cast(BaseTool, SimpleNamespace(name="local_tool")),
            ),
            _grouped_tool("read_query", "mcp-tabular"),
        ],
        mcp_prompt_groups=[
            McpPromptGroup(
                server_id="mcp-tabular", title="tabular action", agent_instructions=None
            )
        ],
    )

    other_header = suffix.index("Other tools:")
    tabular_header = suffix.index("Tools for tabular action:")
    assert other_header < tabular_header
    assert "- local_tool:" in suffix[other_header:tabular_header]


def test_tool_prompt_suffix_keeps_flat_list_with_no_header_when_mcp_prompt_groups_is_empty() -> (
    None
):
    # The Deep-agent call site never passes `mcp_prompt_groups` — a tagged
    # tool must still render as a plain flat bullet, no "Other tools:" noise,
    # byte-identical to a caller with no grouping concept at all.
    suffix = build_runtime_tool_prompt_suffix(
        [_grouped_tool("read_query", "mcp-tabular")]
    )

    assert "Other tools:" not in suffix
    assert "Tools for" not in suffix
    assert "- read_query: Do read_query things." in suffix


def test_tool_prompt_suffix_skips_a_group_with_no_currently_bound_tools() -> None:
    # An active capability whose tools didn't resolve this turn shouldn't
    # leave an empty header for the model to puzzle over.
    suffix = build_runtime_tool_prompt_suffix(
        [_grouped_tool("read_query", "mcp-tabular")],
        mcp_prompt_groups=[
            McpPromptGroup(
                server_id="mcp-tabular", title="tabular action", agent_instructions=None
            ),
            McpPromptGroup(
                server_id="mcp-empty", title="nothing here", agent_instructions=None
            ),
        ],
    )

    assert "nothing here" not in suffix


def test_tool_prompt_suffix_orders_groups_by_the_given_mcp_prompt_groups_sequence() -> (
    None
):
    # Render order follows `mcp_prompt_groups` (the caller's, already
    # id-sorted, order) — not the order tools happen to appear in `bound_tools`.
    suffix = build_runtime_tool_prompt_suffix(
        [
            _grouped_tool("search_documents", "mcp-text"),
            _grouped_tool("read_query", "mcp-tabular"),
        ],
        mcp_prompt_groups=[
            McpPromptGroup(
                server_id="mcp-tabular", title="tabular action", agent_instructions=None
            ),
            McpPromptGroup(
                server_id="mcp-text", title="document search", agent_instructions=None
            ),
        ],
    )

    assert suffix.index("Tools for tabular action:") < suffix.index(
        "Tools for document search:"
    )


def _capability_tool(name: str, description: str) -> BaseTool:
    return cast(BaseTool, SimpleNamespace(name=name, description=description))


def test_tool_prompt_suffix_includes_capability_tools_under_other_tools() -> None:
    # #2455 follow-up (same day): a native Fred capability's tools (e.g.
    # document_access's list_document_tree) reach the model's real
    # tool-calling set through `ToolCarrierMiddleware`, never through
    # `bound_tools` — without `capability_tools` they were invisible in this
    # directory even though the model could call them.
    suffix = build_runtime_tool_prompt_suffix(
        [_grouped_tool("read_query", "mcp-tabular")],
        mcp_prompt_groups=[
            McpPromptGroup(
                server_id="mcp-tabular", title="tabular action", agent_instructions=None
            )
        ],
        capability_tools=[
            _capability_tool("list_document_tree", "Browse the document tree.")
        ],
    )

    other_header = suffix.index("Other tools:")
    tabular_header = suffix.index("Tools for tabular action:")
    assert other_header < tabular_header
    assert (
        "- list_document_tree: Browse the document tree."
        in suffix[other_header:tabular_header]
    )


def test_tool_prompt_suffix_skips_a_capability_tool_already_in_bound_tools() -> None:
    # A capability tool sharing a name with an already-bound tool must not be
    # rendered twice.
    suffix = build_runtime_tool_prompt_suffix(
        [
            BoundTool(
                runtime_name="read_document",
                description="Read one document verbatim.",
                tool=cast(BaseTool, SimpleNamespace(name="read_document")),
            )
        ],
        capability_tools=[_capability_tool("read_document", "A duplicate entry.")],
    )

    assert suffix.count("- read_document:") == 1
    assert "A duplicate entry." not in suffix


def test_tool_prompt_suffix_treats_capability_only_tools_as_available() -> None:
    # `bound_tools` empty but `capability_tools` non-empty must NOT trigger
    # the "no external tool is available" branch.
    suffix = build_runtime_tool_prompt_suffix(
        [], capability_tools=[_capability_tool("read_document", "Read one document.")]
    )

    assert "No external tool is available" not in suffix
    assert "- read_document: Read one document." in suffix


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


def test_attachment_context_suffix_marks_spreadsheets_as_text_not_tabular() -> None:
    suffix = build_attachment_context_suffix(
        _binding(
            "## Attached files\n"
            "- sales.csv [2b6a1cfdbffe4847a4d2f087741f2835]: conversation document"
        )
    )

    # Regression for #2418: fast ingest converts CSV/Excel attachments to
    # markdown text (no tabular artifact, no ReBAC tuple), so the prompt must
    # steer agents away from the tabular/SQL tools, whose fail-closed ReBAC
    # check turns "unknown dataset" into a misleading 403.
    assert "Spreadsheet-like attachments (CSV, XLS, XLSX)" in suffix
    assert "treated as text documents" in suffix
    assert "NOT loaded as SQL-queryable tables" in suffix
    assert "never pass an attachment's uid to the tabular/SQL tools" in suffix


def test_attachment_context_suffix_annotates_each_spreadsheet_line_inline() -> None:
    suffix = build_attachment_context_suffix(
        _binding(
            "## Attached files\n"
            "- sales.csv [2b6a1cfdbffe4847a4d2f087741f2835]: conversation document\n"
            "- Plan_2026.XLSX [77aa1cfdbffe4847a4d2f087741f2899]: conversation document\n"
            "- notes.pdf [88bb1cfdbffe4847a4d2f087741f2811]: conversation document"
        )
    )

    # #2418 follow-up: the paragraph-level rule alone was ignored in live
    # testing, so each spreadsheet line carries the warning inline, next to
    # the uid the model would otherwise feed to the tabular/SQL tools.
    assert (
        "- sales.csv [2b6a1cfdbffe4847a4d2f087741f2835]: conversation document "
        "(markdown text, NOT a SQL dataset - use the conversation search tool, "
        "never the tabular/SQL tools)" in suffix
    )
    # Case-insensitive extension match (.XLSX) is annotated too.
    assert (
        "- Plan_2026.XLSX [77aa1cfdbffe4847a4d2f087741f2899]: conversation document "
        "(markdown text, NOT a SQL dataset" in suffix
    )
    # Non-spreadsheet attachments keep their line untouched.
    assert (
        "- notes.pdf [88bb1cfdbffe4847a4d2f087741f2811]: conversation document\n"
        in suffix
        or suffix.endswith(
            "- notes.pdf [88bb1cfdbffe4847a4d2f087741f2811]: conversation document"
        )
    )
    assert suffix.count("NOT a SQL dataset") == 2


def test_document_scope_suffix_names_the_selection() -> None:
    suffix = build_document_scope_suffix(_binding(selected_document_uids=["u-1"]))

    assert "picked the document(s) listed below" in suffix
    # Without a referent the model asks which file is meant while one is ticked.
    assert "this document" in suffix
    assert "- u-1" in suffix
    assert "NEVER repeat" in suffix
    # A library pick unions with the document pick, so the suffix must not
    # claim the listed documents are all the tools can reach.
    assert "whole libraries" in suffix


def test_document_scope_suffix_is_absent_without_a_selection() -> None:
    assert build_document_scope_suffix(_binding()) == ""
    assert build_document_scope_suffix(_binding(selected_document_uids=[])) == ""


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


def test_compose_system_prompt_folds_selected_prompt_and_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Both ReAct and Deep delegate to this composer, so this single test locks
    # the #1915 fix and the previously-missing Deep attachment suffix at once.
    # A pod file is installed because the platform instructions are pod config
    # (`config/platform_prompt.json`), not a packaged constant — without one
    # there is no instructions block to place in the ordering asserted below.
    _with_pod_file(
        monkeypatch, platform_instructions="# Platform operating instructions"
    )
    prompt = compose_system_prompt(
        "BASE-TEMPLATE",
        binding=_binding(
            "## Attached files\n- report.pdf: conversation document",
            context_prompt_text="Always respond in Spanish.",
        ),
        agent_id="agent-1",
        tool_suffix="\n\nTOOL-SUFFIX",
    )

    assert "BASE-TEMPLATE" in prompt
    assert "TOOL-SUFFIX" in prompt
    assert "Always respond in Spanish." in prompt
    assert "- report.pdf" in prompt
    assert "# Platform operating instructions" in prompt
    # #2412 item 3 follow-up (2026-08-28): a fixed heading marks the
    # boundary into the agent's own template, so it's visible where Fred's
    # shared instructions end and the agent-specific block begins.
    assert "# Agent instructions" in prompt
    # Ordering (#2412 item 3, 2026-08-27): general instructions, then tools,
    # then the agent's own template as the LAST static block — for
    # recency (the agent's instructions should be closest to the model's
    # answer) and provider prefix-cache reuse (the stable prefix shared
    # across agents on a deployment now extends through "tools" instead of
    # ending after the first few characters) — then the volatile per-turn
    # tail: the selected prompt, then the freshest block, the attachment.
    # 2026-08-31: the platform instructions lead, right under the (absent here)
    # admin-editable platform prompt — the two platform-wide layers read as one
    # section — and the Mermaid output contract stays after them.
    assert prompt.index("# Platform operating instructions") < prompt.index(
        _EXPECTED_MERMAID_FRAGMENT
    )
    assert prompt.index(_EXPECTED_MERMAID_FRAGMENT) < prompt.index("TOOL-SUFFIX")
    assert prompt.index("TOOL-SUFFIX") < prompt.index("# Agent instructions")
    assert prompt.index("# Agent instructions") < prompt.index("BASE-TEMPLATE")
    assert prompt.index("BASE-TEMPLATE") < prompt.index("Always respond in Spanish.")
    assert prompt.index("Always respond in Spanish.") < prompt.index("- report.pdf")


def test_compose_system_prompt_places_runtime_suffixes_before_the_agent_template() -> (
    None
):
    # Runtime-specific static notices (e.g. the Deep filesystem suffix) are
    # the "how to use the tools" block (#2412 item 3): after tools, still
    # ahead of both the agent's own template and the per-turn user context.
    prompt = compose_system_prompt(
        "BASE-TEMPLATE",
        binding=_binding(context_prompt_text="Speak Spanish."),
        agent_id="agent-1",
        runtime_suffixes=("\n\nFILESYSTEM-NOTICE",),
    )

    assert "FILESYSTEM-NOTICE" in prompt
    assert prompt.index("FILESYSTEM-NOTICE") < prompt.index("BASE-TEMPLATE")
    assert prompt.index("BASE-TEMPLATE") < prompt.index("Speak Spanish.")


def test_compose_system_prompt_omits_agent_heading_when_template_is_empty() -> None:
    # An agent with no configured `system_prompt_template` passes "" as
    # `base_prompt` (`policy.system_prompt_template or ""` in the callers) —
    # no dangling "# Agent instructions" heading with nothing under it.
    prompt = compose_system_prompt(
        "",
        binding=_binding(),
        agent_id="agent-1",
        tool_suffix="\n\nTOOL-SUFFIX",
    )

    assert "# Agent instructions" not in prompt
    assert "TOOL-SUFFIX" in prompt


# ---------------------------------------------------------------------------
# Platform prompt (platform-wide first block)
# ---------------------------------------------------------------------------


def _with_pod_file(
    monkeypatch: pytest.MonkeyPatch,
    *,
    platform_prompt: str | None = None,
    platform_instructions: str | None = None,
) -> None:
    """Stand in for a pod that loaded `config/platform_prompt.json`.

    Both blocks come off the one file, so one helper sets whichever the test
    cares about and leaves the other unconfigured.
    """

    monkeypatch.setattr(
        react_prompting,
        "get_runtime_context_or_none",
        lambda: SimpleNamespace(
            get_default_platform_prompt=lambda: platform_prompt,
            get_platform_instructions=lambda: platform_instructions,
        ),
    )


def test_platform_prompt_prefix_uses_the_admin_saved_value() -> None:
    assert build_platform_prompt_prefix(_binding(platform_prompt="  BE HELPFUL  ")) == (
        "\n\nBE HELPFUL"
    )


def test_platform_prompt_prefix_is_empty_when_the_pod_shipped_no_file() -> None:
    # No runtime context is set in unit tests, so `get_runtime_context_or_none`
    # returns None — the block must simply be absent, not raise.
    assert build_platform_prompt_prefix(_binding()) == ""


def test_platform_prompt_prefix_empty_admin_value_suppresses_the_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An admin who saves "" means "no platform prompt", which must NOT fall back
    # to the pod file — that distinction is the whole point of `None` vs "",
    # and it is the one an admin cannot express any other way.
    _with_pod_file(monkeypatch, platform_prompt="POD-DEFAULT")
    assert build_platform_prompt_prefix(_binding(platform_prompt="")) == ""


def test_platform_prompt_prefix_falls_back_to_the_pod_file_when_never_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_pod_file(monkeypatch, platform_prompt="POD-DEFAULT")
    assert build_platform_prompt_prefix(_binding()) == "\n\nPOD-DEFAULT"


def test_platform_instructions_prefix_comes_from_the_same_pod_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The read-only block is pod config too, and is NOT overridable per turn:
    # an admin-saved platform prompt must not displace it.
    _with_pod_file(monkeypatch, platform_instructions="HOUSE-RULES")
    assert build_platform_instructions_prefix() == "\n\nHOUSE-RULES"
    assert build_platform_instructions_prefix() == "\n\nHOUSE-RULES"


def test_platform_instructions_prefix_is_empty_when_the_pod_shipped_no_file() -> None:
    assert build_platform_instructions_prefix() == ""


def test_compose_system_prompt_puts_the_platform_prompt_first() -> None:
    prompt = compose_system_prompt(
        "BASE-TEMPLATE",
        binding=_binding(platform_prompt="MASTER-BLOCK"),
        agent_id="agent-1",
        tool_suffix="TOOL-SUFFIX",
    )

    assert prompt.startswith("MASTER-BLOCK")
    assert prompt.index("MASTER-BLOCK") < prompt.index(_EXPECTED_MERMAID_FRAGMENT)
    assert prompt.index("MASTER-BLOCK") < prompt.index("TOOL-SUFFIX")
    assert prompt.index("MASTER-BLOCK") < prompt.index("BASE-TEMPLATE")
