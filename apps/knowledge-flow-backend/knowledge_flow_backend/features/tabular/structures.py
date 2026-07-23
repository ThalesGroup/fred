# Copyright Thales 2025
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

from typing import Literal, Optional

from fred_core.common import OwnerFilter
from pydantic import BaseModel, Field

# -- Constants for consistent types --
DTypes = Literal["string", "integer", "float", "boolean", "datetime", "unknown"]

# "csv" documents carry one table; "spreadsheet" documents (Excel workbooks)
# carry one or more tables extracted at ingestion time.
TabularDocumentKind = Literal["csv", "spreadsheet"]

# -- Schema models --


class TabularColumnSchema(BaseModel):
    name: str
    dtype: DTypes
    sample_values: Optional[list[str]] = Field(
        default=None,
        description=(
            "Every distinct non-null value observed for this column, only when its "
            "cardinality is low enough (see the ingestion threshold) to be useful as "
            "SQL-generation grounding — e.g. the exact stored casing of a status or "
            "severity column. None for high-cardinality or non-string columns."
        ),
    )


class TabularDatasetResponse(BaseModel):
    """
    Authorized dataset summary exposed by the dataset-centric tabular API.

    Why this exists:
    - Callers need one dataset-level payload that already includes the SQL alias
      and schema preview authorized for the current user.

    How to use:
    - Returned by `GET /tabular/datasets`.
    - Reuse `query_alias` directly in SQL statements executed via `/tabular/query`.
    """

    document_uid: str
    document_name: str
    query_alias: str
    row_count: Optional[int] = None
    columns: list[TabularColumnSchema] = Field(default_factory=list)
    tag_ids: list[str] = Field(default_factory=list)
    tag_names: list[str] = Field(default_factory=list)
    source_tag: Optional[str] = None
    generated_at: Optional[str] = None


class TabularTableSummary(BaseModel):
    """
    Lightweight description of one queryable table of a document.

    Why this exists:
    - The document list must stay cheap for LLM context: table identity and
      size, but no column detail (that is the schemas endpoint's job).

    How to use:
    - Returned inside `TabularDocumentResponse.tables`.
    - Use `query_alias` directly as the relation name in `/tabular/query` SQL.
    """

    query_alias: str
    sheet: Optional[str] = None
    title: Optional[str] = None
    row_count: Optional[int] = None
    generated_at: Optional[str] = None


class TabularDocumentResponse(BaseModel):
    """
    Authorized tabular document exposed by the document-centric tabular API.

    Why this exists:
    - Agents pick sources at document level: one CSV maps to one table, one
      Excel workbook maps to several. Listing per table would repeat the
      document identity N times.

    How to use:
    - Returned by `GET /tabular/documents`.
    - Follow up with `GET /tabular/documents/schemas` for column-level detail.
    """

    document_uid: str
    document_name: str
    kind: TabularDocumentKind
    tables: list[TabularTableSummary] = Field(default_factory=list)
    tag_ids: list[str] = Field(default_factory=list)
    tag_names: list[str] = Field(default_factory=list)
    source_tag: Optional[str] = None


class TabularTableSchema(TabularTableSummary):
    """
    Full schema for one queryable table (summary fields plus columns).

    Why this exists:
    - Schema inspection is table-level for multi-table documents; every table
      of a workbook must be visible, not only the first one.

    How to use:
    - Returned inside `TabularDocumentSchemaResponse.tables`.
    """

    columns: list[TabularColumnSchema] = Field(default_factory=list)


class TabularDocumentSchemaResponse(BaseModel):
    """
    Full schema description for one authorized tabular document.

    Why this exists:
    - One batch call must cover CSV datasets and multi-table Excel workbooks
      alike, returning every table of each requested document.

    How to use:
    - Returned by `GET /tabular/documents/schemas` (one entry per requested
      document uid).
    """

    document_uid: str
    document_name: str
    kind: TabularDocumentKind
    tables: list[TabularTableSchema] = Field(default_factory=list)
    source_tag: Optional[str] = None


class TabularDocumentMarkdownResponse(BaseModel):
    """
    Markdown catalog of one spreadsheet document.

    Why this exists:
    - The spreadsheet `output.md` is the human/LLM-readable extraction catalog:
      per sheet it lists each table's title and context, cell ranges, the exact
      `query_alias`, the name of every identified column, and any residual text
      left on the sheet.

    How to use:
    - Returned by `GET /tabular/documents/{document_uid}/markdown`.
    """

    document_uid: str
    content: str


class TabularQueryRequest(BaseModel):
    """
    Read-only SQL query request for authorized tabular datasets.

    Why this exists:
    - The new tabular runtime can query several document-scoped datasets at once.

    How to use:
    - Send `sql` and an optional `dataset_uids` subset.
    - Leave `dataset_uids` empty to query every readable dataset in the active
      tabular scope.
    - Optionally pass `owner_filter`, `team_id`, and
      `document_library_tags_ids` so SQL execution stays inside the current
      personal/team area and selected libraries.

    Example:
    ```python
    request = TabularQueryRequest(
        sql="SELECT city, COUNT(*) FROM d_doc_sales GROUP BY city",
        dataset_uids=["doc-sales"],
        owner_filter=OwnerFilter.TEAM,
        team_id="team-a",
        max_rows=50,
    )
    ```
    """

    sql: str = Field(..., min_length=1)
    dataset_uids: Optional[list[str]] = None
    document_library_tags_ids: Optional[list[str]] = Field(
        default=None,
        description="Optional list of library tag IDs used to keep the query inside selected libraries.",
    )
    owner_filter: Optional[OwnerFilter] = Field(
        default=None,
        description="Optional ownership scope: 'personal' or 'team'.",
    )
    team_id: Optional[str] = Field(
        default=None,
        description="Team ID required when owner_filter is 'team'.",
    )
    max_rows: Optional[int] = Field(default=None, ge=1)

    @property
    def sql_text(self) -> str:
        """
        Return the normalized SQL text carried by the dataset-centric request.

        Why this exists:
        - Service code should execute one trimmed SQL string without duplicating
          normalization logic.

        How to use:
        - Use `request.sql_text` in the execution service.
        """

        return self.sql.strip()


class RawSQLResponse(BaseModel):
    sql_query: str
    rows: list[dict] = Field(default_factory=list)
    error: Optional[str] = None
    dataset_uids: list[str] = Field(default_factory=list)
    query_aliases: list[str] = Field(default_factory=list)


# Value-locator bounds. These are ceilings, not just defaults: a broad search
# must never flood the agent context, so a caller may lower them but never raise
# them. See EXCEL-EXTRACTION-PIPELINE-RFC §12 (INGEST-04).
SEARCH_MAX_ROWS_PER_TABLE = 5
SEARCH_MAX_MATCHING_TABLES = 30


class TabularSearchRequest(BaseModel):
    """
    Keyword value-locator request over authorized tabular datasets.

    Why this exists:
    - The catalog and schemas expose a workbook's structure but never its cell
      values, so a question about a value otherwise forces a blind table-by-table
      scan — one MCP/LLM round trip per table. This locates the value once,
      server-side.

    How to use:
    - Send a precise `keyword`; scope with `dataset_uids` when possible (one
      spreadsheet uid covers all its tables). Leave `dataset_uids` empty to search
      every readable dataset in the active scope.
    - `max_rows_per_table` and `max_matching_tables` are ceilings (module
      constants) — lower them, never raise them.

    Example:
    ```python
    request = TabularSearchRequest(keyword="ABC-123", dataset_uids=["doc-sales"])
    ```
    """

    keyword: str = Field(
        ...,
        min_length=1,
        description="Word or expression to locate. Use precise values only: a generic term matches too many tables and cannot disambiguate.",
    )
    dataset_uids: Optional[list[str]] = None
    document_library_tags_ids: Optional[list[str]] = Field(
        default=None,
        description="Optional list of library tag IDs used to keep the search inside selected libraries.",
    )
    owner_filter: Optional[OwnerFilter] = Field(
        default=None,
        description="Optional ownership scope: 'personal' or 'team'.",
    )
    team_id: Optional[str] = Field(
        default=None,
        description="Team ID required when owner_filter is 'team'.",
    )
    max_rows_per_table: int = Field(
        default=SEARCH_MAX_ROWS_PER_TABLE,
        ge=1,
        le=SEARCH_MAX_ROWS_PER_TABLE,
        description="Maximum matching rows returned per table (ceiling).",
    )
    max_matching_tables: int = Field(
        default=SEARCH_MAX_MATCHING_TABLES,
        ge=1,
        le=SEARCH_MAX_MATCHING_TABLES,
        description="Maximum tables with a match returned before the search stops (ceiling).",
    )


class TabularTableMatch(BaseModel):
    """
    One table in which the searched keyword was found.

    Why this exists:
    - The agent needs to know exactly which table and which columns hold the
      value, and to see a bounded sample of matching rows, before issuing one
      targeted `read_query`.

    How to use:
    - Returned inside `TabularSearchResponse.matches`.
    - Query the table via its `query_alias`; `matched_columns` names the columns
      to filter on.
    """

    document_uid: str
    document_name: str
    query_alias: str
    sheet: Optional[str] = None
    title: Optional[str] = None
    matched_columns: list[str] = Field(default_factory=list)
    rows: list[dict] = Field(default_factory=list)
    row_truncated: bool = Field(
        default=False,
        description="True when more matching rows existed than were returned (max_rows_per_table reached): other occurrences remain in this table.",
    )


class TabularSearchResponse(BaseModel):
    """
    Result of a keyword value-locator search.

    Why this exists:
    - One payload tells the agent where a value occurs and warns when the result
      is partial, so it refines the keyword instead of trusting a truncated
      picture.

    How to use:
    - Returned by `POST /tabular/search`.
    - When `tables_truncated` is true the search stopped at the table cap: the
      keyword is too generic to disambiguate — refine it or read the catalog.
    """

    keyword: str
    normalized_keyword: str
    matches: list[TabularTableMatch] = Field(default_factory=list)
    tables_truncated: bool = Field(
        default=False,
        description="True when the max_matching_tables cap was reached: other tables may also contain the value.",
    )
    searched_dataset_uids: list[str] = Field(default_factory=list)
