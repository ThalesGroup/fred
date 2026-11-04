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
    is_categorical: Optional[bool] = Field(
        default=None,
        description=(
            "For string columns, whether the count of distinct non-null values is "
            "between 1 and max_categories(row_count), with null rows included in "
            "row_count. None for non-string or older columns without this analysis."
        ),
    )
    has_two_values: Optional[bool] = Field(
        default=None,
        description=("For string columns, whether exactly two distinct non-null values were observed. This does not assign true/false meaning to those values."),
    )
    sample_values: Optional[list[str]] = Field(
        default=None,
        description=("Every distinct non-null string value when is_categorical is true, preserving exact casing for SQL filters. None otherwise."),
    )
    min_value: int | float | None = Field(
        default=None,
        description="Smallest finite non-null value of an integer or float column. None when unavailable.",
    )
    max_value: int | float | None = Field(
        default=None,
        description="Largest finite non-null value of an integer or float column. None when unavailable.",
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
      size, but no column detail (that is the description endpoint's job).

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
    - Used internally to assemble the compact `GET /tabular/documents` response.
    - Follow up with `GET /tabular/documents/schemas` for the extraction catalog
      and column-level detail.
    """

    document_uid: str
    document_name: str
    kind: TabularDocumentKind
    tables: list[TabularTableSummary] = Field(default_factory=list)
    tag_ids: list[str] = Field(default_factory=list)
    tag_names: list[str] = Field(default_factory=list)
    source_tag: Optional[str] = None
    source_kind: Literal["corpus", "conversation_attachment"] = "corpus"


class TabularDocumentListTableResponse(BaseModel):
    """Excel table identity exposed by the document-list endpoint."""

    query_alias: str
    sheet: Optional[str] = None
    title: Optional[str] = None


class TabularDocumentListResponse(BaseModel):
    """Document name and identifiers needed by later tabular tools."""

    document_uid: str
    document_name: str
    tables: Optional[list[TabularDocumentListTableResponse]] = None
    source_kind: Literal["corpus", "conversation_attachment"] = "corpus"
    tag_names: list[str] | None = None


class TabularTableSchema(TabularTableSummary):
    """
    Full schema for one queryable table (summary fields plus columns).

    Why this exists:
    - Schema inspection is table-level for multi-table documents; every table
      of a workbook must be visible, not only the first one.

    How to use:
    - Returned inside `TabularDocumentDescriptionResponse.tables`.
    """

    columns: list[TabularColumnSchema] = Field(default_factory=list)


class TabularDocumentDescriptionResponse(BaseModel):
    """
    Extraction catalog and full schemas for one authorized tabular document.

    Why this exists:
    - One batch call must return the workbook context before its typed tables,
      while CSV documents expose their typed table without a catalog.

    How to use:
    - Returned by `GET /tabular/documents/schemas` (one entry per requested
      document uid).
    """

    document_uid: str
    document_name: str
    kind: TabularDocumentKind
    markdown: str | None
    tables: list[TabularTableSchema] = Field(default_factory=list)
    source_tag: Optional[str] = None


class TabularQueryRequest(BaseModel):
    """
    One read-only DuckDB SELECT over authorized document tables.

    sql uses discovered table aliases; dataset_uids scopes exact document UIDs.
    If omitted, SQL may reference any table in the active authorized scope;
    only referenced tables are mounted. The query must read at least one table
    and respect the server's dataset limit. Scope parameters do not grant access.
    max_rows caps the returned preview; compute totals and statistics in SQL.
    """

    sql: str = Field(
        ...,
        min_length=1,
        description="One read-only DuckDB SELECT using exact tables[].query_alias values from describe_tabular_documents. These aliases are SQL table names, not document UIDs or filenames.",
    )
    dataset_uids: Optional[list[str]] = Field(
        default=None, description="Document UIDs copied exactly from authorized discovery. One workbook UID selects all its tables. Do not pass filenames, SQL aliases or shortened identifiers."
    )
    attachment_uids: list[str] | None = Field(default=None, max_length=1000, description="Explicit uploader-owned attachment UIDs; runtime supplies the authorized conversation inventory.")
    include_session_scope: bool = True
    include_corpus_scope: bool = True
    corpus_document_uids: list[str] | None = None
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
    max_rows: Optional[int] = Field(
        default=None, ge=1, description="Maximum result rows to return, capped by the server. For totals or statistics, aggregate in SQL rather than counting this preview."
    )

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
    message: str | None = Field(
        default=None, description="Explicit success explanation when the query returned zero rows; not an error or a claim that the whole document has no relevant information."
    )
    dataset_uids: list[str] = Field(default_factory=list)
    query_aliases: list[str] = Field(default_factory=list)


# Value-locator bounds. These are ceilings, not just defaults: a broad search
# must never flood the agent context, so a caller may lower them but never raise
# them. See EXCEL-EXTRACTION-PIPELINE-RFC §12 (INGEST-04).
SEARCH_MAX_ROWS_PER_TABLE = 5
SEARCH_MAX_MATCHING_TABLES = 30


class TabularSearchRequest(BaseModel):
    """
    Bounded lookup of a precise value after inspecting document structure.

    Schemas expose types and categorical values; this locator helps find other
    cell values across tables. dataset_uids scopes exact document UIDs, with
    one workbook UID covering all its tables. If omitted, all readable datasets
    in the active scope may be searched. Prefer a narrow scope and keyword.
    Preview ceilings can be lowered, never raised; truncation means partial
    coverage and requires refining the search.
    """

    keyword: str = Field(
        ...,
        min_length=1,
        description="Precise word or expression of at least two characters after trimming. Use after document description; generic terms match too many tables to locate a value.",
    )
    dataset_uids: Optional[list[str]] = Field(
        default=None, description="Document UIDs copied exactly from authorized discovery. Do not pass filenames or SQL table aliases. One workbook UID selects all its tables."
    )
    attachment_uids: list[str] | None = Field(default=None, max_length=1000, description="Explicit uploader-owned attachment UIDs; runtime supplies the authorized conversation inventory.")
    include_session_scope: bool = True
    include_corpus_scope: bool = True
    corpus_document_uids: list[str] | None = None
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
    - When `tables_truncated` is true the result is partial, for one of two
      reasons: the keyword matched more tables than `max_matching_tables` (it is
      too generic — refine it), or the scope held more datasets than one request
      may scan (scope it with `dataset_uids`). Compare `searched_dataset_uids`
      with what you expected to tell the two apart.
    """

    keyword: str
    normalized_keyword: str
    matches: list[TabularTableMatch] = Field(default_factory=list)
    tables_truncated: bool = Field(
        default=False,
        description="True when the result is partial: either the max_matching_tables cap was reached, or the scope exceeded the number of datasets one search may scan. Other tables may also contain the value.",
    )
    searched_dataset_uids: list[str] = Field(
        default_factory=list,
        description="Documents that were in scope for this search. A document dropped by the dataset limit is omitted entirely. Note this is not proof a listed document was read exhaustively: when tables_truncated is true the scan stopped early, so a listed document may still hold the keyword in a table that was never opened.",
    )
