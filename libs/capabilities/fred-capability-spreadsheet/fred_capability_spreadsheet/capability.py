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

"""`SpreadsheetCapability`: one tool that turns tabular data into a downloadable `.xlsx`.

Tool-only (`tools()`), so it runs on ReAct, Deep and Graph agents. The file and a
JSON preview go through `RuntimeServices.workspace_fs`; the chat shows a card that
opens the preview pane, or a plain download chip when the preview is missing.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from functools import wraps
from typing import Any, Literal, cast

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
    SidePanelSpec,
)
from fred_sdk.contracts.context import (
    LinkKind,
    LinkPart,
    PublishedArtifact,
    ToolFailure,
    ToolFailureCode,
    ToolInvocationResult,
    UiPart,
)
from fred_sdk.contracts.runtime import WorkspaceFsPort
from httpx import HTTPError, HTTPStatusError
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, ValidationError

from fred_capability_spreadsheet.revisions import (
    ChangeError,
    apply_changes,
    describe,
    normalize_spec,
)
from fred_capability_spreadsheet.source import (
    MAX_SOURCE_BYTES,
    WorkbookSource,
    embed_source,
    read_source,
)
from fred_capability_spreadsheet.workbook import (
    CreateSpreadsheetInput,
    SheetSpec,
    SpreadsheetInputError,
    build_preview,
    build_workbook,
    derived_column_hints,
    manual_total_hints,
    prepare,
    sanitize_file_name,
    total_notes,
)

logger = logging.getLogger(__name__)

SPREADSHEET_CAPABILITY_ID = "spreadsheet"
TOOL_NAME = "create_spreadsheet"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PREVIEW_CONTENT_TYPE = "application/json"
PANE_WIDGET = "spreadsheet_pane"

# Per-pod bound on concurrent workbook builds so a burst cannot exhaust the
# shared to_thread pool; over the bound we fail fast, never queue (as PPT Filler).
MAX_CONCURRENT_BUILDS = 4
_active_builds = 0

_TOOL_DESCRIPTION = (
    "Create an Excel file (.xlsx) the user can download. Call this tool whenever "
    "the user asks, in any wording or language, for an Excel file, a spreadsheet, "
    "an .xlsx, or a table to download; never paste a Markdown table instead.\n"
    "Charts are not supported yet: if the user asks for a chart, still create the "
    "workbook with its data, and tell the user plainly that charts are not "
    "available yet (they can insert one in Excel from the data).\n"
    "Each sheet has typed columns (text, number, integer, percent, currency, date) "
    "and rows holding exactly one value per column (null for an empty cell).\n"
    "Never compute derived columns yourself: when a column is derived from other "
    "columns (difference, ratio, rate, share of total, VAT...), set formula on the "
    "column so the file keeps a live formula: the formula of row 2, filled down "
    '(null for it in rows; $ on a cell every row reads). Use IFERROR(...,"") when a '
    "divisor may be 0. Example: columns [{header: 'HT', type: 'currency'}, {header: "
    "'TTC', type: 'currency', formula: '=A2*1.2'}, {header: 'Part', type: 'percent', "
    "formula: '=A2/SUM($A$2:$A$4)'}], rows [[100, null, null], [250, null, null], "
    "[50, null, null]].\n"
    "Lookups, conditions, text, statistics, finance (PMT, IRR...), dates or a "
    "summary sheet reading other sheets work the same way, or as a cell "
    "{formula: '=...'}. Excel syntax, English names, "
    "commas; another sheet is 'Sheet name'!B2:B20 (row 1 is the header). Never "
    "send a formula as a plain string. Not available: RAND, INDIRECT, OFFSET, "
    "HYPERLINK, LAMBDA, links to other files.\n"
    "Send numbers and amounts as JSON "
    "numbers (1234.5), never as text with thousands separators or currency "
    "symbols. Percents go in a percent column as fractions (0.15) or '15%'. "
    "Dates are 'YYYY-MM-DD'. A currency column may set currency (EUR, USD, GBP, "
    "CHF, JPY, CNY, CAD, AUD).\n"
    "When the user asks for a total, average, min or max of a column, set total "
    "(sum, average, min, max, count) on that column; never add a column or a row "
    "for it: Excel adds the totals row. A total no column aggregate gives (e.g. "
    "the overall evolution %) is a {formula: '=...'} cell. Set language to the "
    "conversation's language ('fr' or 'en') for the totals label.\n"
    "Limits: 10 sheets, 50 columns, 5000 rows per sheet, 50000 cells. If the data "
    "exceeds a limit, tell the user plainly what the limit is and suggest "
    "splitting the data; never drop rows silently. If the tool returns an error, "
    "fix the input it names and call it again.\n"
    "Call this tool once per file. After a successful creation, do not call it "
    "again for the same file unless its result notes something to fix: answer "
    "the user. For a change the user asks to a "
    "file you created (add a column or rows, edit values, split a sheet...), send "
    "only changes with document_id and expected_content_id from that file's result: "
    "everything else stays as delivered. Never choose a source silently: if its "
    "references are missing, call with changes to obtain bounded candidates. "
    "Choose the file the user means, asking them if ambiguous.\n"
    "If you are a sub-agent working for another agent, do not call this tool: "
    "return the data (as a compact table or JSON) to the agent that delegated to "
    "you; that agent creates one workbook for the user.\n"
    "A download button is shown to the user automatically: do not write a link or "
    "URL in your reply, just say briefly what the file contains."
)


class SpreadsheetPreviewPart(BaseModel):
    """`spreadsheet_preview` chat part: the card that opens the preview pane.

    Both hrefs use the conversation-scoped Control Plane file endpoints; the part
    is persisted with the conversation; the frontend fetches them at open time.
    """

    type: Literal["spreadsheet_preview"] = "spreadsheet_preview"
    document_id: str
    content_id: str
    preview_id: str
    file_name: str
    xlsx_download_url: str
    preview_url: str
    # Versions of one workbook share an id; the chat marks the highest as latest.
    workbook_id: str | None = None
    version: int | None = None


@dataclass(frozen=True)
class _Outputs:
    content: bytes
    preview: bytes | None
    hints: list[str]
    totals: list[str]
    notes: list[str]
    summary: str
    computed_at: str | None = None


def _build_finished(
    task: asyncio.Task[tuple[_Outputs, WorkbookSource, list[str], str]],
) -> None:
    global _active_builds
    _active_builds -= 1
    # A cancelled caller no longer awaits the worker's eventual exception.
    if not task.cancelled():
        task.exception()


def _build_outputs(request: CreateSpreadsheetInput, source: WorkbookSource) -> _Outputs:
    prepared = prepare(request)
    content = embed_source(build_workbook(prepared), source)
    summary = describe(
        [
            (s.name, s.headers, len(s.rows), s.totals is not None)
            for s in prepared.sheets
        ]
    )
    try:
        hints = derived_column_hints(prepared)
    except Exception:
        logger.exception("[SPREADSHEET] derived-column check failed")
        hints = []
    try:
        totals = manual_total_hints(prepared)
        notes = total_notes(prepared)
    except Exception:
        logger.exception("[SPREADSHEET] manual-total check failed")
        totals, notes = [], []
    try:
        preview = build_preview(prepared)
    except Exception:
        # The preview is a convenience: never lose the file over it.
        logger.exception("[SPREADSHEET] preview build failed")
        preview = None
    computed_at = (
        prepared.computed_at.date().isoformat() if prepared.computed_at else None
    )
    return _Outputs(content, preview, hints, totals, notes, summary, computed_at)


async def _preview_part(
    workspace: WorkspaceFsPort,
    preview: bytes | None,
    path: str,
    published: PublishedArtifact,
    visible_name: str,
    workbook_id: str,
    version: int,
) -> UiPart | None:
    """Publish a preview of this exact primary content; no sibling user file."""

    if preview is None or not published.href or not published.content_id:
        return None
    try:
        stored = await workspace.write(
            path,
            preview,
            expected_content_id=published.content_id,
            source_content_id=published.content_id,
            content_type=PREVIEW_CONTENT_TYPE,
            title=f"{visible_name}.preview.json",
        )
    except (HTTPError, OSError, ValueError):
        logger.warning(
            "[SPREADSHEET] preview upload failed (file still returned)", exc_info=True
        )
        return None
    if not stored.href:
        return None
    part = SpreadsheetPreviewPart(
        document_id=published.document_uid or published.key,
        content_id=published.content_id,
        preview_id=published.key,
        file_name=f"{visible_name}.xlsx",
        xlsx_download_url=published.href,
        preview_url=stored.href,
        workbook_id=workbook_id,
        version=version,
    )
    # Capability parts join the runtime UiPart union at registry boot.
    return cast(UiPart, part)


def _error(
    message: str, code: ToolFailureCode = ToolFailureCode.invalid_arguments
) -> tuple[str, ToolInvocationResult]:
    return message, ToolInvocationResult(
        tool_ref=TOOL_NAME, failure=ToolFailure(code=code)
    )


def _created_text(
    output_file_name: str,
    hints: Sequence[str] = (),
    totals: Sequence[str] = (),
    charts_ignored: bool = False,
    summary: str = "",
    computed_at: str | None = None,
    notes: Sequence[str] = (),
) -> str:
    note = (
        " Note: these columns hold values you computed, so the file has no formula "
        f"for them: {'; '.join(hints)}. Next time, set formula on such columns "
        "instead of computing the values yourself."
        if hints
        else ""
    )
    if totals:
        note += (
            f" Note: {'; '.join(totals)} looks like a manual total next to the "
            "automatic totals row; next time, leave totals to total."
        )
    note += "".join(f" Note: {text}" for text in notes)
    if charts_ignored:
        note += (
            " Note: charts are not supported yet; the workbook was created without "
            "the chart. Tell the user."
        )
    if computed_at:
        note += (
            f" Note: TODAY/NOW values were computed at build time ({computed_at}); "
            "Excel updates them when the file opens."
        )
    later = (
        " To change it later, call create_spreadsheet with changes, document_id "
        f"and expected_content_id from this result. {summary}."
    )
    # With a note the model may send a fix (as changes) or just reply.
    ending = (
        " If a note applies, you may send the fix as changes; otherwise reply now."
        if note
        else " Do not create it again; reply now."
    )
    return (
        f"The Excel file '{output_file_name}' has a download button in the chat; "
        f"do not write a download link.{note}{later} File created and shown to the "
        f"user.{ending}"
    )


class SpreadsheetToolInput(CreateSpreadsheetInput):
    """Source selection belongs to the tool, not the pure workbook engine."""

    document_id: str | None = Field(
        default=None, description="UUID of the exact conversation XLSX to change."
    )
    expected_content_id: str | None = Field(
        default=None, description="Content UUID returned for that source XLSX."
    )


def _build_tool(ctx: CapabilityContext[EmptyModel, EmptyModel]) -> BaseTool:
    workspace = ctx.services.workspace_fs
    session_id = ctx.identity.session_id
    # Only an intra-turn duplicate guard. CP owns concurrent publication.
    created: dict[str, tuple[str, ToolInvocationResult]] = {}
    call_lock = asyncio.Lock()

    async def create_spreadsheet(
        file_name: str | None = None,
        sheets: list[SheetSpec] | None = None,
        language: str | None = None,
        changes: list[dict[str, Any]] | None = None,
        charts_ignored: bool = False,
        document_id: str | None = None,
        expected_content_id: str | None = None,
    ) -> tuple[str, ToolInvocationResult]:
        if workspace is None or not session_id:
            return _error(
                "File output requires a bound conversation. Do not retry.",
                ToolFailureCode.misconfigured,
            )
        if bool(sheets) == bool(changes):
            return _error("No file was written: send either sheets or changes.")
        if not changes and (document_id or expected_content_id):
            return _error("Source references are only accepted with changes.")
        if changes and (not document_id or not expected_content_id):
            try:
                page = await workspace.list(limit=20)
            except (HTTPError, OSError, ValueError):
                return _error(
                    "Source candidates could not be read. Try again later.",
                    ToolFailureCode.service_error,
                )
            candidates = [
                {
                    "file_name": row.name,
                    "document_id": row.document_id,
                    "expected_content_id": row.content_id,
                }
                for row in page
                if row.mime == XLSX_CONTENT_TYPE
            ]
            return _error(
                "No file was written: supply document_id and expected_content_id "
                "for the file the user means. These are candidates among the 20 "
                "newest conversation files, not a complete catalogue. Do not choose "
                "silently if ambiguous: ask which file. Candidates: "
                + json.dumps(candidates, ensure_ascii=False)
            )
        if changes:
            try:
                document_id = str(uuid.UUID(cast(str, document_id)))
                expected_content_id = str(uuid.UUID(cast(str, expected_content_id)))
            except ValueError:
                return _error("Source references must be UUIDs from a file result.")
        global _active_builds
        if _active_builds >= MAX_CONCURRENT_BUILDS:
            return _error(
                "The server is busy creating Excel files. Try again in a moment.",
                ToolFailureCode.service_busy,
            )
        _active_builds += 1
        build = None
        try:
            source_bytes: bytes | None = None
            if changes:
                try:
                    snapshot = await workspace.read(
                        cast(str, document_id), max_bytes=MAX_SOURCE_BYTES
                    )
                except HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        return _error(
                            "The source file no longer exists in this conversation.",
                            ToolFailureCode.resource_unavailable,
                        )
                    return _error(
                        "The source file could not be read. Try again later.",
                        ToolFailureCode.service_error,
                    )
                except (HTTPError, OSError):
                    return _error(
                        "The source file could not be read. Try again later.",
                        ToolFailureCode.service_error,
                    )
                except ValueError:
                    return _error(
                        "The source file exceeds the read limit or has invalid identity metadata."
                    )
                if snapshot.content_id != expected_content_id:
                    return _error(
                        "The source content changed. Select its current references before retrying; no file was written."
                    )
                source_bytes = snapshot.content
            # Decode, validate, revise and build share the bounded worker slot.
            build = asyncio.create_task(
                asyncio.to_thread(
                    _build_revision,
                    source_bytes,
                    changes,
                    file_name,
                    sheets,
                    language,
                )
            )
            build.add_done_callback(_build_finished)
            try:
                outputs, source, row_report, request_key = await asyncio.shield(build)
            except (SpreadsheetInputError, ChangeError) as exc:
                return _error(f"No file was written. {exc}")
        finally:
            # A cancelled read has no worker callback to release the slot.
            if build is None:
                _active_builds -= 1
        call_key = f"{expected_content_id or 'new'}:{request_key}"
        if call_key in created:
            return created[call_key]
        base_name = source.file_name
        visible_name = (
            base_name if source.version == 1 else f"{base_name}-v{source.version}"
        )
        output_file_name = f"{visible_name}.xlsx"
        # Source content alone selects the successor path across pods and requests.
        # Business names cannot fork that successor or inject a path.
        folder = f"outputs/{session_id}/spreadsheets"
        if expected_content_id:
            path = f"{folder}/revisions/{expected_content_id}/{base_name}-v{source.version}.xlsx"
        else:
            path = f"{folder}/{uuid.uuid4()}/{output_file_name}"
        try:
            published = await workspace.write(
                path,
                outputs.content,
                expected_content_id=None,
                content_type=XLSX_CONTENT_TYPE,
                title=output_file_name,
            )
        except HTTPStatusError as exc:
            if exc.response.status_code == 409:
                return _error(
                    "A successor of this source already exists or is being published. Select the intended current file from the conversation before applying more changes; no rebase was performed."
                )
            return _error(
                "The Excel file could not be stored. Try again later.",
                ToolFailureCode.service_error,
            )
        except (HTTPError, OSError, ValueError):
            return _error(
                "The Excel file could not be stored. Try again later.",
                ToolFailureCode.service_error,
            )
        part = await _preview_part(
            workspace,
            outputs.preview,
            path,
            published,
            visible_name,
            str(source.workbook_id),
            source.version,
        )
        if part is None:
            part = LinkPart(
                href=published.href,
                title=output_file_name,
                kind=LinkKind.download,
                mime=XLSX_CONTENT_TYPE,
                document_uid=published.document_uid,
                file_name=output_file_name,
            )
        text = _created_text(
            output_file_name,
            outputs.hints,
            outputs.totals,
            charts_ignored,
            outputs.summary,
            outputs.computed_at,
            [*outputs.notes, *row_report],
        )
        text = (
            f"Source references: document_id={published.document_uid or published.key}; "
            f"expected_content_id={published.content_id}. "
        ) + text
        result = text, ToolInvocationResult(tool_ref=TOOL_NAME, ui_parts=(part,))
        created[call_key] = result
        return result

    @wraps(create_spreadsheet)
    async def guarded_create_spreadsheet(
        **kwargs: Any,
    ) -> tuple[str, ToolInvocationResult]:
        if call_lock.locked():
            return _error(
                "Another spreadsheet call is running in this turn. Retry after it finishes.",
                ToolFailureCode.service_busy,
            )
        async with call_lock:
            return await create_spreadsheet(**kwargs)

    return StructuredTool.from_function(
        coroutine=guarded_create_spreadsheet,
        name=TOOL_NAME,
        description=_TOOL_DESCRIPTION,
        args_schema=SpreadsheetToolInput,
        response_format="content_and_artifact",
    )


def _build_revision(
    source_bytes: bytes | None,
    changes: list[dict[str, Any]] | None,
    file_name: str | None,
    sheets: list[SheetSpec] | None,
    language: str | None,
) -> tuple[_Outputs, WorkbookSource, list[str], str]:
    base = read_source(source_bytes) if source_bytes is not None else None
    if base is not None:
        if base.version >= 1_000_000:
            raise ChangeError(
                "The source reached its revision limit; create a new workbook."
            )
        # Revision naming is inherited, independent of caller-supplied file_name.
        if file_name and sanitize_file_name(file_name) != base.file_name:
            raise ChangeError(
                "Keep the source name for a revision; create a new workbook to rename it."
            )
        file_name = base.file_name
    request, request_key, spec_json, row_report = _resolve_request(
        base.spec.model_dump_json() if base else None,
        changes,
        file_name,
        sheets,
        language,
    )
    source = WorkbookSource(
        workbook_id=base.workbook_id if base else uuid.uuid4(),
        version=base.version + 1 if base else 1,
        file_name=sanitize_file_name(request.file_name or ""),
        spec=CreateSpreadsheetInput.model_validate_json(spec_json),
    )
    return _build_outputs(request, source), source, row_report, request_key


def _resolve_request(
    base_json: str | None,
    changes: list[dict[str, Any]] | None,
    file_name: str | None,
    sheets: list[SheetSpec] | None,
    language: str | None,
) -> tuple[CreateSpreadsheetInput, str, str, list[str]]:
    """The request to build, its per-turn dedupe key, its stored JSON and the
    rows the changes touched."""

    row_report: list[str] = []
    if base_json is not None and changes:
        spec = apply_changes(json.loads(base_json), changes, row_report)
        if file_name:
            spec["file_name"] = file_name
        if language:
            spec["language"] = language
        try:
            request = CreateSpreadsheetInput.model_validate(spec)
        except ValidationError as exc:
            raise ChangeError(
                "No file was written: the changed workbook is not valid: "
                + "; ".join(
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                    for e in exc.errors()[:5]
                )
            ) from None
    else:
        request = CreateSpreadsheetInput.model_validate(
            {"file_name": file_name, "sheets": sheets, "language": language}
        )
    spec = request_spec(request)
    key_spec = {**spec, "file_name": sanitize_file_name(request.file_name or "")}
    key = hashlib.sha256(
        json.dumps(key_spec, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return request, key, json.dumps(spec, ensure_ascii=False), row_report


def request_spec(request: CreateSpreadsheetInput) -> dict[str, Any]:
    return normalize_spec(request.model_dump(mode="json"))


class SpreadsheetCapability(AgentCapability[EmptyModel, EmptyModel, EmptyModel]):
    """Create downloadable Excel workbooks with a read-only preview pane."""

    manifest = CapabilityManifest(
        id=SPREADSHEET_CAPABILITY_ID,
        version="0.1.0",
        name="capability.spreadsheet.name",
        description="capability.spreadsheet.description",
        icon="table_chart",
        available_to_subagents=False,
        chat_parts=[SpreadsheetPreviewPart],
        side_panels=[SidePanelSpec(widget=PANE_WIDGET)],
    )
    ConfigModel = EmptyModel

    def tools(
        self, ctx: CapabilityContext[EmptyModel, EmptyModel]
    ) -> Sequence[BaseTool]:
        return [_build_tool(ctx)]
