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
import logging
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, cast

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
from pydantic import BaseModel

from fred_capability_spreadsheet.store import WorkbookRow
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
    "columns (difference, ratio, rate, share of total, VAT...), declare it with "
    "compute so the file keeps a live formula, and send null for it in rows. "
    "compute is {op: add|subtract|multiply|divide, left, right}, each operand "
    "another column's header or a number, or {op: share_of_total, column} (each "
    "value divided by that column's total, e.g. a share of the total in a percent "
    "column); optional round (decimals). A division by zero leaves the cell empty, "
    "so divide even when some values are 0. It may use source columns and computed "
    "columns placed before it. Example: columns [{header: 'HT', type: 'currency'}, "
    "{header: 'TTC', type: 'currency', compute: {op: 'multiply', left: 'HT', "
    "right: 1.2}}, {header: 'Part', type: 'percent', compute: {op: "
    "'share_of_total', column: 'HT'}}], rows [[100, null, null]].\n"
    "Other formulas: prefer compute and total. For lookups, conditions, text, "
    "dates or a summary sheet reading other sheets, set formula on a column (the "
    "formula of row 2, filled down; null for it in rows; $ on a cell every row "
    "reads) or send a cell as {formula: '=...'}. Excel syntax, English names, "
    "commas; another sheet is 'Sheet name'!B2:B20 (row 1 is the header). Never "
    "send a formula as a plain string. Not available: TODAY, NOW, INDIRECT, "
    "OFFSET, HYPERLINK, TEXT, links to other files.\n"
    "Send numbers and amounts as JSON "
    "numbers (1234.5), never as text with thousands separators or currency "
    "symbols. Percents go in a percent column as fractions (0.15) or '15%'. "
    "Dates are 'YYYY-MM-DD'. A currency column may set currency (EUR, USD, GBP, "
    "CHF, JPY, CNY, CAD, AUD).\n"
    "For totals or averages, set total (sum, average, min, max, count) on the "
    "column: Excel adds the totals row. Do not add your own total/subtotal row "
    "for columns that set total; the totals row is added automatically. Set "
    "language to the conversation's language ('fr' or 'en') for its label.\n"
    "Limits: 10 sheets, 50 columns, 5000 rows per sheet, 50000 cells. If the data "
    "exceeds a limit, tell the user plainly what the limit is and suggest "
    "splitting the data; never drop rows silently. If the tool returns an error, "
    "fix the input it names and call it again.\n"
    "Call this tool once per file. After a successful creation, do not call it "
    "again for the same file: answer the user. Call it again only to change the "
    "file, with the complete corrected data.\n"
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


def _build_outputs(
    request: CreateSpreadsheetInput,
) -> tuple[bytes, bytes | None, list[str], list[str]]:
    prepared = prepare(request)
    content = build_workbook(prepared)
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
    return content, preview, hints, totals


async def _preview_part(
    workspace: WorkspaceFsPort,
    preview: bytes | None,
    path: str,
    published: PublishedArtifact,
    base_name: str,
) -> UiPart | None:
    """Store the preview beside the file; None falls back to the download chip."""

    if preview is None or not published.href:
        return None
    try:
        stored = await workspace.write(
            path.removesuffix(".xlsx") + ".preview.json",
            preview,
            content_type=PREVIEW_CONTENT_TYPE,
            title=f"{base_name}.preview.json",
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
        file_name=f"{base_name}.xlsx",
        xlsx_download_url=published.href,
        preview_url=stored.href,
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
) -> str:
    note = (
        " Note: these columns hold values you computed, so the file has no formula "
        f"for them: {'; '.join(hints)}. Next time, declare such columns with "
        "compute instead of computing the values yourself."
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
    return (
        f"The Excel file '{output_file_name}' has a download button in the chat; "
        f"do not write a download link.{note} File created and shown to the user. "
        "Do not create it again; reply now."
    )


def _build_tool(ctx: CapabilityContext[EmptyModel, EmptyModel]) -> BaseTool:
    session_id = ctx.identity.session_id
    services = ctx.services
    # Tools are built per turn, so this maps the turn's request hashes to the first
    # success text: a model repeating an identical call gets no second copy.
    created: dict[str, str] = {}

    async def create_spreadsheet(
        file_name: str,
        sheets: list[SheetSpec],
        language: str | None = None,
        charts_ignored: bool = False,
    ) -> tuple[str, ToolInvocationResult]:
        request = CreateSpreadsheetInput.model_validate(
            {"file_name": file_name, "sheets": sheets, "language": language}
        )
        request_key = hashlib.sha256(
            request.model_copy(
                update={"file_name": sanitize_file_name(request.file_name)}
            )
            .model_dump_json()
            .encode()
        ).hexdigest()
        if request_key in created:
            logger.info("[SPREADSHEET] identical repeat call skipped")
            return created[request_key], ToolInvocationResult(tool_ref=TOOL_NAME)
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
            content, preview, hints, totals = await asyncio.to_thread(
                _build_outputs, request
            )
        except SpreadsheetInputError as exc:
            logger.info("[SPREADSHEET] rejected input: %s", exc)
            return _error(f"No file was written. {exc}")
        finally:
            _active_builds -= 1

        base_name = sanitize_file_name(request.file_name)
        output_file_name = f"{base_name}.xlsx"
        folder = f"spreadsheets/{session_id}" if session_id else "spreadsheets"
        path = f"{folder}/{base_name}-{uuid.uuid4().hex[:8]}.xlsx"
        try:
            published = await workspace.write(
                path, content, content_type=XLSX_CONTENT_TYPE, title=output_file_name
            )
        except Exception as exc:
            logger.exception("[SPREADSHEET] upload failed path=%s", path)
            return _error(
                f"The Excel file was built but could not be stored "
                f"[{type(exc).__name__}]. Tell the user to try again later."
            )

        part = await _preview_part(workspace, preview, path, published, base_name)
        if part is None:
            part = LinkPart(
                href=published.href,
                title=output_file_name,
                kind=LinkKind.download,
                mime=XLSX_CONTENT_TYPE,
                document_uid=published.document_uid,
                file_name=output_file_name,
            )
        logger.info(
            "[SPREADSHEET] created session=%s key=%s sheets=%d bytes=%d",
            session_id,
            published.key,
            len(request.sheets),
            len(content),
        )
        if hints:
            logger.info("[SPREADSHEET] literal derived columns=%d", len(hints))
        if totals:
            logger.info("[SPREADSHEET] manual total rows=%d", len(totals))
        if charts_ignored:
            logger.info("[SPREADSHEET] chart arguments ignored")
        text = _created_text(output_file_name, hints, totals, charts_ignored)
        created[request_key] = text
        return text, ToolInvocationResult(tool_ref=TOOL_NAME, ui_parts=(part,))

    return StructuredTool.from_function(
        coroutine=create_spreadsheet,
        name=TOOL_NAME,
        description=_TOOL_DESCRIPTION,
        args_schema=CreateSpreadsheetInput,
        response_format="content_and_artifact",
    )


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
