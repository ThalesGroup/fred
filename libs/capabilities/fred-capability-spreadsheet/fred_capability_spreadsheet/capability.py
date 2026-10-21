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

Tool-only (`tools()`), so it runs on ReAct, Deep and Graph agents. The file goes
through `RuntimeServices.workspace_fs` and reaches the chat as a download chip.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Sequence

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
)
from fred_sdk.contracts.context import LinkKind, LinkPart, ToolInvocationResult
from langchain_core.tools import BaseTool, StructuredTool

from fred_capability_spreadsheet.workbook import (
    CreateSpreadsheetInput,
    SheetSpec,
    SpreadsheetInputError,
    build_workbook,
    sanitize_file_name,
)

logger = logging.getLogger(__name__)

SPREADSHEET_CAPABILITY_ID = "spreadsheet"
TOOL_NAME = "create_spreadsheet"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_TOOL_DESCRIPTION = (
    "Create an Excel file (.xlsx) the user can download. Call this tool whenever "
    "the user asks, in any wording or language, for an Excel file, a spreadsheet, "
    "an .xlsx, or a table to download; never paste a Markdown table instead.\n"
    "Each sheet has typed columns (text, number, integer, percent, currency, date) "
    "and rows holding exactly one value per column (null for an empty cell). "
    "Dates are 'YYYY-MM-DD'; percents are fractions (0.15) or strings ('15%'); "
    "a currency column may set currency (EUR, USD, GBP, CHF, JPY, CNY, CAD, AUD). "
    "Set total (sum, average, min, max, count) on a column to add a totals row "
    "computed by Excel; never compute totals yourself. Limits: 10 sheets, 50 "
    "columns, 5000 rows per sheet, 50000 cells. If the tool returns an error, fix "
    "the input it names and call it again.\n"
    "A download button is shown to the user automatically: do not write a link or "
    "URL in your reply, just say briefly what the file contains."
)


def _error(message: str) -> tuple[str, ToolInvocationResult]:
    return message, ToolInvocationResult(tool_ref=TOOL_NAME, is_error=True)


def _build_tool(ctx: CapabilityContext[EmptyModel, EmptyModel]) -> BaseTool:
    session_id = ctx.identity.session_id
    services = ctx.services

    async def create_spreadsheet(
        file_name: str, sheets: list[SheetSpec]
    ) -> tuple[str, ToolInvocationResult]:
        request = CreateSpreadsheetInput.model_validate(
            {"file_name": file_name, "sheets": sheets}
        )
        workspace = services.workspace_fs
        if workspace is None:
            logger.error("[SPREADSHEET] workspace_fs is not available on this runtime")
            return _error(
                "The Excel file could not be created: file output is not available "
                "on this platform. Tell the user; do not retry."
            )
        try:
            content = await asyncio.to_thread(build_workbook, request)
        except SpreadsheetInputError as exc:
            logger.info("[SPREADSHEET] rejected input: %s", exc)
            return _error(f"No file was written. {exc}")

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

        link = LinkPart(
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
        return (
            (
                f"The Excel file '{output_file_name}' was created. A download button "
                "is shown to the user automatically; do not write a download link "
                "yourself."
            ),
            ToolInvocationResult(tool_ref=TOOL_NAME, ui_parts=(link,)),
        )

    return StructuredTool.from_function(
        coroutine=create_spreadsheet,
        name=TOOL_NAME,
        description=_TOOL_DESCRIPTION,
        args_schema=CreateSpreadsheetInput,
        response_format="content_and_artifact",
    )


class SpreadsheetCapability(AgentCapability[EmptyModel, EmptyModel, EmptyModel]):
    """Create downloadable Excel workbooks. No config, table, router or chat part."""

    manifest = CapabilityManifest(
        id=SPREADSHEET_CAPABILITY_ID,
        version="0.1.0",
        name="capability.spreadsheet.name",
        description="capability.spreadsheet.description",
        icon="table_chart",
    )
    ConfigModel = EmptyModel

    def tools(
        self, ctx: CapabilityContext[EmptyModel, EmptyModel]
    ) -> Sequence[BaseTool]:
        return [_build_tool(ctx)]
