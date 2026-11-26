# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Self-contained XLSX revisions and conversation publication boundaries."""

from __future__ import annotations

import asyncio
import io
import json
import zipfile
from uuid import uuid4

import pytest
from fred_capability_spreadsheet import capability, source
from fred_capability_spreadsheet.source import read_source
from fred_capability_spreadsheet.workbook import SpreadsheetInputError
from fred_runtime.runtime_support.authority import AuthorityLostError
from langgraph.errors import GraphInterrupt
from openpyxl import load_workbook
from test_capability import ARGS, FakeWorkspace, _tool

CHANGE = [{"op": "add_rows", "sheet": "Budget", "rows": [["Training", 100]]}]


@pytest.mark.asyncio
async def test_revision_uses_explicit_snapshot_in_a_new_turn():
    workspace = FakeWorkspace()
    _, first = await _tool(workspace)(**ARGS)
    references = workspace.references()
    original = workspace.files[references["document_id"]][1]
    text, second = await _tool(workspace)(changes=CHANGE, **references)
    assert not second.is_error, text
    part = second.ui_parts[0]
    assert part.version == 2 and part.workbook_id == first.ui_parts[0].workbook_id
    assert part.document_id != references["document_id"]
    assert part.file_name == "Q3 budget-v2.xlsx"
    rendered = workspace.files[part.document_id][1]
    assert (
        load_workbook(io.BytesIO(rendered), data_only=True)["Budget"]["A4"].value
        == "Training"
    )
    assert read_source(rendered).spec.sheets[0].rows[-1] == ["Training", 100]
    assert workspace.files[references["document_id"]][1] == original
    assert len(await workspace.list()) == 2


@pytest.mark.asyncio
async def test_same_named_creations_start_independent_lineages():
    workspace = FakeWorkspace()
    _, first = await _tool(workspace)(**ARGS)
    _, second = await _tool(workspace)(**ARGS)
    assert first.ui_parts[0].workbook_id != second.ui_parts[0].workbook_id
    assert first.ui_parts[0].version == second.ui_parts[0].version == 1


@pytest.mark.asyncio
async def test_missing_references_offer_candidates_without_selecting(monkeypatch):
    workspace = FakeWorkspace()
    await _tool(workspace)(**ARGS)

    async def unexpected_read(*args, **kwargs):
        pytest.fail("A candidate must never be selected silently")

    monkeypatch.setattr(workspace, "read", unexpected_read)
    text, result = await _tool(workspace)(changes=CHANGE)
    assert result.is_error and workspace.references()["document_id"] in text
    assert "20 newest" in text and len(workspace.files) == 1


@pytest.mark.asyncio
async def test_changed_content_fails_before_build(monkeypatch):
    workspace = FakeWorkspace()
    await _tool(workspace)(**ARGS)
    references = {**workspace.references(), "expected_content_id": str(uuid4())}

    def unexpected(*args):
        pytest.fail("Stale input must fail before build")

    monkeypatch.setattr(capability, "_build_revision", unexpected)
    text, result = await _tool(workspace)(changes=CHANGE, **references)
    assert result.is_error and "content changed" in text
    assert len(workspace.files) == 1


@pytest.mark.asyncio
async def test_two_instances_cannot_publish_two_successors():
    workspace = FakeWorkspace()
    await _tool(workspace)(**ARGS)
    references = workspace.references()
    other = [{"op": "add_rows", "sheet": "Budget", "rows": [["Other", 200]]}]
    results = await asyncio.gather(
        _tool(workspace)(changes=CHANGE, **references),
        _tool(workspace)(changes=other, **references),
    )
    assert sorted(result.is_error for _, result in results) == [False, True]
    assert "successor" in next(text for text, result in results if result.is_error)
    assert len(workspace.files) == 2
    del workspace.files[list(workspace.files)[-1]]
    text, result = await _tool(workspace)(changes=CHANGE, **references)
    assert not result.is_error, text


@pytest.mark.asyncio
async def test_rename_cannot_fork_the_successor_path():
    workspace = FakeWorkspace()
    await _tool(workspace)(**ARGS)
    text, result = await _tool(workspace)(
        changes=CHANGE, file_name="different", **workspace.references()
    )
    assert result.is_error and "Keep the source name" in text
    assert len(workspace.files) == 1


@pytest.mark.asyncio
async def test_source_deleted_after_read_keeps_snapshot_semantics(monkeypatch):
    workspace = FakeWorkspace()
    await _tool(workspace)(**ARGS)
    references = workspace.references()
    read = workspace.read

    async def read_and_delete(document_id, *, max_bytes):
        snapshot = await read(document_id, max_bytes=max_bytes)
        del workspace.files[document_id]
        return snapshot

    monkeypatch.setattr(workspace, "read", read_and_delete)
    text, result = await _tool(workspace)(changes=CHANGE, **references)
    assert not result.is_error, text
    assert result.ui_parts[0].version == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["list", "read", "write", "preview"])
@pytest.mark.parametrize(
    "failure", [AuthorityLostError, GraphInterrupt, asyncio.CancelledError]
)
async def test_authority_interrupt_cancellation_propagate(monkeypatch, phase, failure):
    workspace = FakeWorkspace()
    await _tool(workspace)(**ARGS)
    references = workspace.references()
    original_write = workspace.write

    async def fail(*args, **kwargs):
        if phase == "preview" and not kwargs.get("source_content_id"):
            return await original_write(*args, **kwargs)
        raise failure()

    monkeypatch.setattr(workspace, "write" if phase == "preview" else phase, fail)
    with pytest.raises(failure):
        await _tool(workspace)(
            changes=CHANGE, **({} if phase == "list" else references)
        )


@pytest.mark.asyncio
async def test_excel_edit_rejects_spec_even_when_custom_xml_is_preserved():
    workspace = FakeWorkspace()
    await _tool(workspace)(**ARGS)
    content = next(iter(workspace.files.values()))[1]
    entries = source._entries(content)
    entries["xl/worksheets/sheet1.xml"] = entries["xl/worksheets/sheet1.xml"].replace(
        b"1200", b"9999"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    with pytest.raises(SpreadsheetInputError, match="modified outside Fred"):
        read_source(buffer.getvalue())


@pytest.mark.parametrize(
    "kind", ["corrupt", "unsupported", "duplicate", "too_large", "uncompressed"]
)
def test_bounded_distinct_source_failures(monkeypatch, kind):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", b"xml")
        archive.writestr("[Content_Types].xml", b"xml")
        if kind == "duplicate":
            with pytest.warns(UserWarning, match="Duplicate"):
                archive.writestr("xl/workbook.xml", b"xml")
    content = buffer.getvalue()
    if kind == "corrupt":
        content = b"broken"
    elif kind == "too_large":
        monkeypatch.setattr(source, "MAX_SOURCE_BYTES", 1)
    elif kind == "uncompressed":
        monkeypatch.setattr(source, "MAX_UNCOMPRESSED_BYTES", 1)
    expected = {
        "corrupt": "corrupt",
        "unsupported": "no supported",
        "duplicate": "duplicate",
        "too_large": "32 MiB",
        "uncompressed": "uncompressed",
    }[kind]
    with pytest.raises(SpreadsheetInputError, match=expected):
        read_source(content)


@pytest.mark.asyncio
async def test_preview_is_json_of_its_exact_xlsx():
    workspace = FakeWorkspace()
    _, result = await _tool(workspace)(**ARGS)
    part = result.ui_parts[0]
    assert part.content_id == workspace.files[part.document_id][0].content_id
    assert json.loads(workspace.previews[part.document_id])["sheets"][0]["totals"] == [
        "Total",
        1550.5,
    ]
