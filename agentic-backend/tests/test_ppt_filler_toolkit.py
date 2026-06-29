"""Offline, fixture-driven tests for the PPT Filler fill tool (PPTFILL-05 / #1834).

Decks are built in-test with python-pptx (no checked-in binaries), reusing the helper
style of ``tests/test_ppt_filler_parser.py``. The workspace client is faked the way
``tests/test_kf_vector_search_tools.py`` fakes its HTTP client, so everything is offline:
no network, no real ApplicationContext.

Coverage (the acceptance criteria of #1834):

- The dynamic ``args_schema`` is generated per-slide from a given ``schema_slides``, with
  each leaf carrying its note description.
- Filling uses the shared traversal and fills repeated keys on a slide with the same value.
- The filled deck is uploaded to SESSION-SCOPED user storage and a download ``LinkPart`` is
  returned.
- No remaining ``{{keys}}`` after filling all provided fields.
"""

import io
from typing import List, Optional, Tuple

import pytest
from pptx import Presentation
from pptx.util import Inches

from agentic_backend.common import kf_workspace_client as kf_ws
from agentic_backend.common.kf_workspace_client import (
    UserStorageBlob,
    UserStorageUploadResult,
)
from agentic_backend.common.structures import AgentSettings, AgentTuning
from agentic_backend.core.agents.agent_spec import MCPServerRef
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.chatbot.chat_schema import LinkKind, LinkPart
from agentic_backend.integrations.ppt_filler.parser import parse
from agentic_backend.integrations.ppt_filler.ppt_filler_params import (
    PPT_FILLER_TEMPLATE_KEY,
    PptFillerParams,
)
from agentic_backend.integrations.ppt_filler.toolkit import build_ppt_filler_tools
from agentic_backend.integrations.ppt_filler.traversal import KEY_PATTERN

_PPTX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)


# --- Deck-builder fixtures (mirrors tests/test_ppt_filler_parser.py) --------------

# (text-box body, notes text) per slide.
SlideSpec = Tuple[str, str]


def _build_deck(slides: List[SlideSpec]) -> bytes:
    """Build a ``.pptx`` with one text box and one notes block per slide spec."""
    presentation = Presentation()
    blank_layout = presentation.slide_layouts[6]  # blank
    for body, notes in slides:
        slide = presentation.slides.add_slide(blank_layout)
        textbox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(2))
        textbox.text_frame.text = body
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def _schema_slides(deck: bytes):
    """Parse a deck and return its persisted-style ``schema_slides`` list."""
    return parse(deck).slides


# --- Fakes ------------------------------------------------------------------------


class _FakeAgent:
    """Minimal KnowledgeFlowAgentContext stand-in carrying ppt_filler params."""

    def __init__(self, *, params: PptFillerParams, session_id: Optional[str] = None):
        self.agent_settings = AgentSettings(
            id="agent-1",
            name="PPT Filler",
            tuning=AgentTuning(
                role="r",
                description="d",
                mcp_servers=[MCPServerRef(id="mcp-ppt-filler", params=params)],
            ),
        )
        self.runtime_context = RuntimeContext(session_id=session_id, access_token="tok")

    def refresh_user_access_token(self) -> str:
        raise NotImplementedError("not exercised by these tests")


class _FakeWorkspaceClient:
    """Records fetch/upload calls and serves a configured template blob.

    Substituted for the real ``KfWorkspaceClient`` so the tool runs fully offline.
    """

    template_bytes: bytes = b""
    fetch_calls: list[dict] = []
    upload_calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        # The tool constructs ``KfWorkspaceClient(agent=agent)``; accept and ignore.
        pass

    async def fetch_agent_config_blob(self, key, access_token=None, agent_id=None):
        type(self).fetch_calls.append(
            {"key": key, "access_token": access_token, "agent_id": agent_id}
        )
        return UserStorageBlob(
            bytes=type(self).template_bytes,
            content_type=_PPTX_CONTENT_TYPE,
            filename=key,
            size=len(type(self).template_bytes),
        )

    async def upload_user_blob(self, key, file_content, filename, content_type=None):
        content = (
            file_content
            if isinstance(file_content, (bytes, bytearray))
            else file_content.read()
        )
        type(self).upload_calls.append(
            {
                "key": key,
                "content": bytes(content),
                "filename": filename,
                "content_type": content_type,
            }
        )
        return UserStorageUploadResult(
            key=key,
            file_name=filename,
            size=len(content),
            document_uid="doc-uid-123",
            download_url=f"https://example.test/storage/user/{key}",
        )


@pytest.fixture
def fake_ws(monkeypatch):
    """Install a fresh fake KfWorkspaceClient for one test."""

    class _Client(_FakeWorkspaceClient):
        template_bytes = b""
        fetch_calls = []
        upload_calls = []

    monkeypatch.setattr(kf_ws, "KfWorkspaceClient", _Client)
    # The toolkit imported the symbol by name, so patch it there too.
    import agentic_backend.integrations.ppt_filler.toolkit as toolkit_mod

    monkeypatch.setattr(toolkit_mod, "KfWorkspaceClient", _Client)
    return _Client


def _the_tool(agent):
    tools = build_ppt_filler_tools(agent)
    assert len(tools) == 1
    return tools[0]


# --- A. Dynamic per-slide args_schema ---------------------------------------------


def test_args_schema_is_nested_by_slide_with_leaf_descriptions():
    deck = _build_deck(
        [
            (
                "Hello {{name}} and {{role}}",
                "{{name}}:\nThe person's name\n{{role}}:\nTheir role",
            ),
            ("City: {{city}}", "{{city}}:\nThe city"),
        ]
    )
    params = PptFillerParams(schema=_schema_slides(deck))
    tool = _the_tool(_FakeAgent(params=params))

    schema = tool.args_schema.model_json_schema()

    # Top-level groups are keyed by slide_<n> (1-based slide numbers), plus an optional
    # output_file_name the model can set to name the produced deck.
    assert set(schema["properties"]) == {"slide_1", "slide_2", "output_file_name"}
    # Slide groups are required; output_file_name is optional.
    assert set(schema["required"]) == {"slide_1", "slide_2"}
    assert "output_file_name" not in schema.get("required", [])

    # Resolve the $ref of each slide group to its leaf object and assert leaf keys +
    # descriptions are present.
    defs = schema["$defs"]

    def _leaf(slide_field: str) -> dict:
        ref = schema["properties"][slide_field]["$ref"]
        return defs[ref.split("/")[-1]]

    slide1 = _leaf("slide_1")
    assert set(slide1["properties"]) == {"name", "role"}
    assert slide1["properties"]["name"]["description"] == "The person's name"
    assert slide1["properties"]["role"]["description"] == "Their role"

    slide2 = _leaf("slide_2")
    assert set(slide2["properties"]) == {"city"}
    assert slide2["properties"]["city"]["description"] == "The city"


def test_no_tool_when_schema_is_empty():
    """No persisted schema (template never configured) -> nothing to fill -> no tool."""
    agent = _FakeAgent(params=PptFillerParams())
    assert build_ppt_filler_tools(agent) == []


# --- B/C/D. Fill via shared traversal, upload, return LinkPart --------------------


@pytest.mark.asyncio
async def test_fill_repeated_keys_on_slide_uses_one_value(fake_ws):
    """A key appearing twice on one slide is filled with the same value (the shared
    run-merging traversal does this), and the deck is uploaded session-scoped with a
    download LinkPart returned."""
    deck = _build_deck(
        [
            (
                "Title {{name}} ... footer {{name}}",
                "{{name}}:\nThe name",
            ),
        ]
    )
    fake_ws.template_bytes = deck
    params = PptFillerParams(schema=_schema_slides(deck), template_key="custom.pptx")
    tool = _the_tool(_FakeAgent(params=params, session_id="sess-9"))

    content, artifact = await tool.coroutine(slide_1={"name": "Jane Doe"})

    # Template fetched from agent-config storage under the configured key + agent_id.
    assert fake_ws.fetch_calls == [
        {"key": "custom.pptx", "access_token": "tok", "agent_id": "agent-1"}
    ]

    # Uploaded to SESSION-SCOPED user storage.
    assert len(fake_ws.upload_calls) == 1
    upload = fake_ws.upload_calls[0]
    assert upload["key"].startswith("sess-9/")
    assert upload["content_type"] == _PPTX_CONTENT_TYPE

    # The uploaded deck has both occurrences filled with the same value and no leftover
    # placeholders.
    filled = Presentation(io.BytesIO(upload["content"]))
    text = "".join(
        run.text
        for shape in filled.slides[0].shapes
        if shape.has_text_frame
        for paragraph in shape.text_frame.paragraphs
        for run in paragraph.runs
    )
    assert text.count("Jane Doe") == 2
    assert not KEY_PATTERN.search(text)

    # The returned artifact carries a download LinkPart with sensible name/mime.
    assert artifact.is_error is False
    assert len(artifact.ui_parts) == 1
    link = artifact.ui_parts[0]
    assert isinstance(link, LinkPart)
    assert link.kind == LinkKind.download
    assert link.mime == _PPTX_CONTENT_TYPE
    assert link.file_name == "filled_presentation.pptx"
    assert link.href and link.href.startswith("https://example.test/storage/user/")
    assert isinstance(content, str) and content.strip()


@pytest.mark.asyncio
async def test_fill_all_fields_leaves_no_placeholders(fake_ws):
    """Filling every provided field across multiple slides leaves NO {{keys}} in the
    produced bytes (re-open and assert)."""
    deck = _build_deck(
        [
            ("Hello {{name}}, the {{role}}", "{{name}}, {{role}}:\nName then role"),
            (
                "Repeated {{name}} and {{city}}",
                "{{name}}:\nName again\n{{city}}:\nThe city",
            ),
        ]
    )
    fake_ws.template_bytes = deck
    params = PptFillerParams(schema=_schema_slides(deck))
    tool = _the_tool(_FakeAgent(params=params, session_id="sess-1"))

    content, artifact = await tool.coroutine(
        slide_1={"name": "Alice", "role": "Engineer"},
        slide_2={"name": "Alice", "city": "Paris"},
    )

    assert artifact.is_error is False
    upload = fake_ws.upload_calls[0]
    refilled = Presentation(io.BytesIO(upload["content"]))
    for slide in refilled.slides:
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            assert not KEY_PATTERN.search(shape.text_frame.text)


@pytest.mark.asyncio
async def test_fill_without_session_uses_unscoped_key(fake_ws):
    """No session_id -> the upload key is the bare output file name (no session prefix)."""
    deck = _build_deck([("{{name}}", "{{name}}:\nThe name")])
    fake_ws.template_bytes = deck
    params = PptFillerParams(schema=_schema_slides(deck))
    tool = _the_tool(_FakeAgent(params=params, session_id=None))

    await tool.coroutine(slide_1={"name": "Bob"})

    assert fake_ws.upload_calls[0]["key"] == "filled_presentation.pptx"


@pytest.mark.asyncio
async def test_default_template_key_is_used(fake_ws):
    """With the default params, the template is fetched under PPT_FILLER_TEMPLATE_KEY."""
    deck = _build_deck([("{{name}}", "{{name}}:\nThe name")])
    fake_ws.template_bytes = deck
    params = PptFillerParams(schema=_schema_slides(deck))
    tool = _the_tool(_FakeAgent(params=params, session_id="s"))

    await tool.coroutine(slide_1={"name": "X"})

    assert fake_ws.fetch_calls[0]["key"] == PPT_FILLER_TEMPLATE_KEY


@pytest.mark.asyncio
async def test_template_fetch_failure_returns_error_result(fake_ws):
    """A template fetch failure becomes an is_error tool result, not a raised exception."""
    deck = _build_deck([("{{name}}", "{{name}}:\nThe name")])
    params = PptFillerParams(schema=_schema_slides(deck))
    tool = _the_tool(_FakeAgent(params=params, session_id="s"))

    async def boom(self, *a, **k):
        raise RuntimeError("storage down")

    fake_ws.fetch_agent_config_blob = boom  # type: ignore[assignment]

    content, artifact = await tool.coroutine(slide_1={"name": "X"})

    assert artifact.is_error is True
    assert artifact.ui_parts == ()
    assert "template" in content.lower()


# --- E. Runtime invocation path preserves the download artifact -------------------


@pytest.mark.asyncio
async def test_ainvoke_with_plain_args_preserves_download_artifact(fake_ws):
    """Regression guard for the dropped download link.

    The v2 ReAct resolver invokes inprocess provider tools via
    ``tool.ainvoke(<plain args dict>)`` and then normalizes the raw return value
    (see ``react_tool_resolution._resolve_runtime_provider_tool``). If the tool were
    declared with ``response_format="content_and_artifact"``, LangChain would return
    ONLY the content string on a plain-args invoke and silently drop the artifact —
    so the download ``LinkPart`` would never reach the UI. This test exercises that
    exact path end to end: ``ainvoke`` must yield the bare ``(content, artifact)``
    tuple, and the resolver's normalization must surface the download link.
    """
    from agentic_backend.core.agents.v2.react.react_tool_rendering import (
        normalize_runtime_provider_artifact,
        render_tool_result,
        stringify_tool_output,
    )

    deck = _build_deck([("{{name}}", "{{name}}:\nThe name")])
    fake_ws.template_bytes = deck
    params = PptFillerParams(schema=_schema_slides(deck))
    tool = _the_tool(_FakeAgent(params=params, session_id="sess-rt"))

    # The runtime calls ainvoke with PLAIN ARGS (not a ToolCall dict). With
    # content_and_artifact this would collapse to a bare content string.
    raw = await tool.ainvoke({"slide_1": {"name": "Ada"}})
    assert isinstance(raw, tuple) and len(raw) == 2, (
        "fill tool must return a (content, artifact) tuple on a plain-args ainvoke; "
        "do not set response_format='content_and_artifact' (it drops the artifact)"
    )

    # Mirror the resolver's normalization branch and assert the link survives.
    rendered = stringify_tool_output(raw[0]).strip()
    artifact = normalize_runtime_provider_artifact(raw[1])
    content = rendered if rendered else render_tool_result(artifact)

    assert content.strip()
    assert artifact is not None
    assert artifact.is_error is False
    assert len(artifact.ui_parts) == 1
    link = artifact.ui_parts[0]
    assert isinstance(link, LinkPart)
    assert link.kind == LinkKind.download
    assert link.file_name == "filled_presentation.pptx"


# --- F. Model-chosen output file name ---------------------------------------------


@pytest.mark.asyncio
async def test_output_file_name_is_used_for_key_and_download(fake_ws):
    """A model-provided output_file_name names the stored blob and the download link,
    and the ".pptx" extension is added when omitted."""
    deck = _build_deck([("{{name}}", "{{name}}:\nThe name")])
    fake_ws.template_bytes = deck
    params = PptFillerParams(schema=_schema_slides(deck))
    tool = _the_tool(_FakeAgent(params=params, session_id="sess-7"))

    _content, artifact = await tool.coroutine(
        slide_1={"name": "Ada"}, output_file_name="Proposition ACME 2026"
    )

    # Stored under the session-scoped key using the chosen name + added extension.
    upload = fake_ws.upload_calls[0]
    assert upload["key"] == "sess-7/Proposition ACME 2026.pptx"
    assert upload["filename"] == "Proposition ACME 2026.pptx"
    # The download link carries the same name.
    assert artifact.ui_parts[0].file_name == "Proposition ACME 2026.pptx"


@pytest.mark.asyncio
async def test_output_file_name_existing_extension_not_doubled(fake_ws):
    """If the model already includes a (case-insensitive) .pptx, it is not doubled."""
    deck = _build_deck([("{{name}}", "{{name}}:\nThe name")])
    fake_ws.template_bytes = deck
    params = PptFillerParams(schema=_schema_slides(deck))
    tool = _the_tool(_FakeAgent(params=params, session_id="s"))

    await tool.coroutine(slide_1={"name": "X"}, output_file_name="Deck.PPTX")

    assert fake_ws.upload_calls[0]["filename"] == "Deck.pptx"


@pytest.mark.asyncio
async def test_output_file_name_strips_path_components(fake_ws):
    """Path separators are stripped (no traversal): only the final component is kept."""
    deck = _build_deck([("{{name}}", "{{name}}:\nThe name")])
    fake_ws.template_bytes = deck
    params = PptFillerParams(schema=_schema_slides(deck))
    tool = _the_tool(_FakeAgent(params=params, session_id="s"))

    await tool.coroutine(slide_1={"name": "X"}, output_file_name="../../etc/evil.pptx")

    upload = fake_ws.upload_calls[0]
    assert upload["filename"] == "evil.pptx"
    assert upload["key"] == "s/evil.pptx"


@pytest.mark.asyncio
async def test_blank_output_file_name_falls_back_to_default(fake_ws):
    """A blank/whitespace name (or just an extension) falls back to the default."""
    deck = _build_deck([("{{name}}", "{{name}}:\nThe name")])
    fake_ws.template_bytes = deck
    params = PptFillerParams(schema=_schema_slides(deck))
    tool = _the_tool(_FakeAgent(params=params, session_id="s"))

    await tool.coroutine(slide_1={"name": "X"}, output_file_name="   ")
    assert fake_ws.upload_calls[0]["filename"] == "filled_presentation.pptx"


# --- G. Notes: authoring guidance stripped; kept content preserved ----------------


def _slide_notes(presentation, index: int) -> str:
    slide = list(presentation.slides)[index]
    if not slide.has_notes_slide:
        return ""
    return slide.notes_slide.notes_text_frame.text or ""


@pytest.mark.asyncio
async def test_filled_deck_strips_authoring_notes(fake_ws):
    """The ``{{key}}:`` descriptions are internal guidance and must NOT appear in the
    filled deck. A slide whose notes are authoring-only ends up with empty notes."""
    deck = _build_deck([("Hello {{name}}", "{{name}}:\nThe person's name")])
    fake_ws.template_bytes = deck
    params = PptFillerParams(schema=_schema_slides(deck))
    tool = _the_tool(_FakeAgent(params=params, session_id="s"))

    await tool.coroutine(slide_1={"name": "Ada"})

    filled = Presentation(io.BytesIO(fake_ws.upload_calls[0]["content"]))
    notes = _slide_notes(filled, 0)
    assert "{{name}}" not in notes
    assert "The person's name" not in notes
    assert notes == ""


@pytest.mark.asyncio
async def test_filled_deck_keeps_notes_after_separator(fake_ws):
    """Content after a ``---`` keep-separator is preserved as the slide's real notes,
    while the authoring description above it is removed."""
    deck = _build_deck(
        [
            (
                "Hello {{name}}",
                "{{name}}:\nThe person's name\n---\nSpeaker note: pause here.",
            )
        ]
    )
    fake_ws.template_bytes = deck
    params = PptFillerParams(schema=_schema_slides(deck))
    tool = _the_tool(_FakeAgent(params=params, session_id="s"))

    await tool.coroutine(slide_1={"name": "Ada"})

    filled = Presentation(io.BytesIO(fake_ws.upload_calls[0]["content"]))
    notes = _slide_notes(filled, 0)
    assert notes == "Speaker note: pause here."
    assert "{{name}}" not in notes
    # And the body was still filled.
    body = "".join(
        run.text
        for shape in list(filled.slides)[0].shapes
        if shape.has_text_frame
        for paragraph in shape.text_frame.paragraphs
        for run in paragraph.runs
    )
    assert "Ada" in body
