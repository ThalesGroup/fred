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
from pathlib import Path
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
    ToolInvocationResult,
    UiPart,
)
from fred_sdk.contracts.runtime import WorkspaceFsPort
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ValidationError

from fred_capability_spreadsheet.revisions import (
    NO_BASE,
    ChangeError,
    apply_changes,
    describe,
    normalize_spec,
)
from fred_capability_spreadsheet.store import (
    StoredWorkbook,
    WorkbookRow,
    get_workbook_spec_store,
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
# A larger request is delivered but not kept as a base for changes.
MAX_STORED_SPEC_BYTES = 4 * 1024 * 1024
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
    "again for the same file: answer the user. For a change the user asks to a "
    "file you created (add a column or rows, edit values, split a sheet...), send "
    "only changes: everything else stays as delivered.\n"
    "If you are a sub-agent working for another agent, do not call this tool: "
    "return the data (as a compact table or JSON) to the agent that delegated to "
    "you; that agent creates one workbook for the user.\n"
    "A download button is shown to the user automatically: do not write a link or "
    "URL in your reply, just say briefly what the file contains."
)


class SpreadsheetPreviewPart(BaseModel):
    """`spreadsheet_preview` chat part: the card that opens the preview pane.

    Both hrefs are the durable bearer-protected `/fs/download` ones, since the part
    is persisted with the conversation; the frontend fetches them at open time.
    """

    type: Literal["spreadsheet_preview"] = "spreadsheet_preview"
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
    summary: str
    computed_at: str | None = None


def _build_outputs(request: CreateSpreadsheetInput) -> _Outputs:
    prepared = prepare(request)
    content = build_workbook(prepared)
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
    except Exception:
        logger.exception("[SPREADSHEET] manual-total check failed")
        totals = []
    try:
        preview = build_preview(prepared)
    except Exception:
        # The preview is a convenience: never lose the file over it.
        logger.exception("[SPREADSHEET] preview build failed")
        preview = None
    computed_at = (
        prepared.computed_at.date().isoformat() if prepared.computed_at else None
    )
    return _Outputs(content, preview, hints, totals, summary, computed_at)


async def _preview_part(
    workspace: WorkspaceFsPort,
    preview: bytes | None,
    path: str,
    published: PublishedArtifact,
    visible_name: str,
    workbook_id: str,
    version: int,
) -> UiPart | None:
    """Store the preview beside the file; None falls back to the download chip."""

    if preview is None or not published.href:
        return None
    try:
        stored = await workspace.write(
            path.removesuffix(".xlsx") + ".preview.json",
            preview,
            content_type=PREVIEW_CONTENT_TYPE,
            title=f"{visible_name}.preview.json",
        )
    except Exception:
        logger.warning(
            "[SPREADSHEET] preview upload failed (file still returned)", exc_info=True
        )
        return None
    if not stored.href:
        return None
    part = SpreadsheetPreviewPart(
        preview_id=published.key,
        file_name=f"{visible_name}.xlsx",
        xlsx_download_url=published.href,
        preview_url=stored.href,
        workbook_id=workbook_id,
        version=version,
    )
    # Capability parts join the runtime UiPart union at registry boot.
    return cast(UiPart, part)


def _error(message: str) -> tuple[str, ToolInvocationResult]:
    return message, ToolInvocationResult(tool_ref=TOOL_NAME, is_error=True)


def _created_text(
    output_file_name: str,
    hints: Sequence[str] = (),
    totals: Sequence[str] = (),
    charts_ignored: bool = False,
    summary: str = "",
    revisable: bool = True,
    computed_at: str | None = None,
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
        " To change it later, call create_spreadsheet with changes (names and row "
        f"numbers as in this file). {summary}."
        if revisable
        else " This file is too large to keep for later changes: to change it, send "
        "the whole workbook in sheets."
    )
    return (
        f"The Excel file '{output_file_name}' has a download button in the chat; "
        f"do not write a download link.{note}{later} File created and shown to the "
        "user. Do not create it again; reply now."
    )


class _TurnState:
    """Per-turn memory of the tool instance (tools are built per execution request)."""

    def __init__(self) -> None:
        # Request hashes to the first success text: no second copy of a repeat.
        self.created: dict[str, str] = {}
        self.base: StoredWorkbook | None = None
        self.loaded = False
        self.too_large = False


def _build_tool(ctx: CapabilityContext[EmptyModel, EmptyModel]) -> BaseTool:
    session_id = ctx.identity.session_id
    instance_id = ctx.identity.agent_instance_id
    services = ctx.services
    turn = _TurnState()
    durable = bool(session_id and instance_id)

    async def load_base() -> StoredWorkbook | None:
        if not turn.loaded:
            turn.loaded = True
            if durable:
                turn.base = await get_workbook_spec_store().get(
                    cast(str, session_id), cast(str, instance_id)
                )
        return turn.base

    async def create_spreadsheet(
        file_name: str | None = None,
        sheets: list[SheetSpec] | None = None,
        language: str | None = None,
        changes: list[dict[str, Any]] | None = None,
        charts_ignored: bool = False,
    ) -> tuple[str, ToolInvocationResult]:
        if sheets and changes:
            return _error(
                "No file was written: send either sheets (the whole workbook) or "
                "changes (to the last file), not both."
            )
        if not sheets and not changes:
            return _error(
                "No file was written: send sheets (the whole workbook), or changes "
                "to change the last file you created in this conversation."
            )
        # A repeated `changes` call in a turn is the same request, never a second
        # application on top of the first result.
        change_key = (
            hashlib.sha256(
                json.dumps(
                    {"changes": changes, "file_name": file_name, "language": language},
                    sort_keys=True,
                    ensure_ascii=False,
                    default=str,
                ).encode()
            ).hexdigest()
            if changes
            else None
        )
        if change_key in turn.created:
            logger.info("[SPREADSHEET] identical repeat changes skipped")
            return turn.created[change_key], ToolInvocationResult(tool_ref=TOOL_NAME)
        try:
            base = await load_base()
        except Exception as exc:
            logger.warning("[SPREADSHEET] base load failed", exc_info=True)
            if changes:
                return _error(
                    f"No file was written: the previous workbook could not be loaded "
                    f"[{type(exc).__name__}]. Send the whole workbook in sheets."
                )
            base = None
        if changes and base is None:
            return _error(
                "No file was written: the last file is too large to keep for "
                "changes. Send the whole workbook in sheets."
                if turn.too_large
                else NO_BASE
            )
        # Applying changes and serializing a request are CPU work proportional to
        # the workbook (~0.2 s at the cell limit): off the event loop.
        try:
            request, request_key, spec_json = await asyncio.to_thread(
                _resolve_request,
                base.spec_json if changes and base else None,
                changes,
                file_name,
                sheets,
                language,
            )
        except ChangeError as exc:
            logger.info("[SPREADSHEET] rejected changes: %s", exc)
            return _error(str(exc))
        base_name = sanitize_file_name(request.file_name or "")
        same_workbook = base is not None and (
            bool(changes) or base_name == base.file_name
        )
        if request_key in turn.created:
            logger.info("[SPREADSHEET] identical repeat call skipped")
            return turn.created[request_key], ToolInvocationResult(tool_ref=TOOL_NAME)
        workspace = services.workspace_fs
        if workspace is None:
            logger.error("[SPREADSHEET] workspace_fs is not available on this runtime")
            return _error(
                "The Excel file could not be created: file output is not available "
                "on this platform. Tell the user; do not retry."
            )
        global _active_builds
        if _active_builds >= MAX_CONCURRENT_BUILDS:
            return _error(
                "The server is busy creating other Excel files right now. "
                "Please try again in a moment."
            )
        _active_builds += 1
        try:
            outputs = await asyncio.to_thread(_build_outputs, request)
        except SpreadsheetInputError as exc:
            logger.info("[SPREADSHEET] rejected input: %s", exc)
            return _error(f"No file was written. {exc}")
        finally:
            _active_builds -= 1

        lineage = base if same_workbook else None
        workbook_id = lineage.workbook_id if lineage else uuid.uuid4().hex[:12]
        version = lineage.version + 1 if lineage else 1
        visible_name = base_name if version == 1 else f"{base_name}-v{version}"
        output_file_name = f"{visible_name}.xlsx"
        folder = f"spreadsheets/{session_id}" if session_id else "spreadsheets"
        path = f"{folder}/{visible_name}-{uuid.uuid4().hex[:8]}.xlsx"
        try:
            published = await workspace.write(
                path,
                outputs.content,
                content_type=XLSX_CONTENT_TYPE,
                title=output_file_name,
            )
        except Exception as exc:
            logger.exception("[SPREADSHEET] upload failed path=%s", path)
            return _error(
                f"The Excel file was built but could not be stored "
                f"[{type(exc).__name__}]. Tell the user to try again later."
            )

        part = await _preview_part(
            workspace,
            outputs.preview,
            path,
            published,
            visible_name,
            workbook_id,
            version,
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
        revisable = await _remember(
            turn,
            StoredWorkbook(workbook_id, version, base_name, spec_json),
            cast(str, session_id) if durable else None,
            cast(str, instance_id) if durable else None,
        )
        logger.info(
            "[SPREADSHEET] created session=%s key=%s sheets=%d bytes=%d revision=%s",
            session_id,
            published.key,
            len(request.sheets),
            len(outputs.content),
            bool(changes),
        )
        if outputs.hints:
            logger.info("[SPREADSHEET] literal derived columns=%d", len(outputs.hints))
        if outputs.totals:
            logger.info("[SPREADSHEET] manual total rows=%d", len(outputs.totals))
        if charts_ignored:
            logger.info("[SPREADSHEET] chart arguments ignored")
        text = _created_text(
            output_file_name,
            outputs.hints,
            outputs.totals,
            charts_ignored,
            outputs.summary,
            revisable,
            outputs.computed_at,
        )
        turn.created[request_key] = text
        if change_key is not None:
            turn.created[change_key] = text
        return text, ToolInvocationResult(tool_ref=TOOL_NAME, ui_parts=(part,))

    return StructuredTool.from_function(
        coroutine=create_spreadsheet,
        name=TOOL_NAME,
        description=_TOOL_DESCRIPTION,
        args_schema=CreateSpreadsheetInput,
        response_format="content_and_artifact",
    )


async def _remember(
    turn: _TurnState,
    workbook: StoredWorkbook,
    session_id: str | None,
    instance_id: str | None,
) -> bool:
    """Keep the delivered request as the next base; False when too large to keep."""

    spec_json = workbook.spec_json
    too_large = len(spec_json.encode()) > MAX_STORED_SPEC_BYTES
    turn.base = None if too_large else workbook
    turn.too_large = too_large
    turn.loaded = True
    if session_id is None or instance_id is None:
        return not too_large
    store = get_workbook_spec_store()
    try:
        if too_large:
            await store.clear(session_id, instance_id)
        else:
            await store.put(session_id, instance_id, workbook)
    except Exception:
        # The file is delivered; the next turn's base is then the previous one.
        logger.warning("[SPREADSHEET] base store failed", exc_info=True)
    return not too_large


def _resolve_request(
    base_json: str | None,
    changes: list[dict[str, Any]] | None,
    file_name: str | None,
    sheets: list[SheetSpec] | None,
    language: str | None,
) -> tuple[CreateSpreadsheetInput, str, str]:
    """The request to build, its per-turn dedupe key and its stored JSON."""

    if base_json is not None and changes:
        spec = apply_changes(json.loads(base_json), changes)
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
    return request, key, json.dumps(spec, ensure_ascii=False)


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
        chat_parts=[SpreadsheetPreviewPart],
        side_panels=[SidePanelSpec(widget=PANE_WIDGET)],
        tables=[WorkbookRow],
    )
    ConfigModel = EmptyModel

    @classmethod
    def migrations_location(cls) -> str:
        """The capability's own Alembic tree, applied under
        `cap_spreadsheet_alembic_version` by `python -m fred_runtime migrate`."""

        return str(Path(__file__).resolve().parent / "spreadsheet_migrations")

    def tools(
        self, ctx: CapabilityContext[EmptyModel, EmptyModel]
    ) -> Sequence[BaseTool]:
        return [_build_tool(ctx)]
