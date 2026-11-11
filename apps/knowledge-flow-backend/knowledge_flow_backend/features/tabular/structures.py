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

from typing import Any, Literal, Optional

# -- Constants for consistent types --
from fred_knowledge.tabular.structures import DTypes as DTypes
from fred_knowledge.tabular.structures import TabularColumnSchema
from pydantic import BaseModel, ConfigDict, Field, GetJsonSchemaHandler, SerializerFunctionWrapHandler, model_serializer
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

# "csv" documents carry one table; "spreadsheet" documents (Excel workbooks)
# carry one or more tables extracted at ingestion time.
TabularDocumentKind = Literal["csv", "spreadsheet"]

# -- Schema models --


class TabularColumnDescription(BaseModel):
    """Compact public schema, separate from stored ingestion classification."""

    name: str
    dtype: DTypes
    categorical_values: list[str] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Exact distinct non-null categories, preserving spelling and case. Present only for a described categorical string column.",
    )
    min_value: int | float | None = Field(default=None, description="Smallest finite value. Present only for integer/float columns; null if none exist.")
    max_value: int | float | None = Field(default=None, description="Largest finite value. Present only for integer/float columns; null if none exist.")

    @model_serializer(mode="wrap")
    def _compact(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # Pydantic's handler returns the model's heterogeneous field dictionary.
        result = handler(self)
        if self.dtype != "string":
            result.pop("categorical_values", None)
        if self.dtype in {"integer", "float"}:
            result.update(min_value=self.min_value, max_value=self.max_value)
        else:
            result.pop("min_value", None)
            result.pop("max_value", None)
        return result

    @classmethod
    def __get_pydantic_json_schema__(cls, schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        # Advertise the declared fields, not the serializer's generic dictionary.
        if handler.mode == "serialization":
            schema = schema.copy()
            schema.pop("serialization", None)
        return handler(schema)

    @classmethod
    def from_stored(cls, column: TabularColumnSchema, *, values_read: bool = False) -> "TabularColumnDescription":
        return cls(
            name=column.name,
            dtype=column.dtype,
            categorical_values=(column.sample_values or []) if values_read and column.dtype == "string" and column.is_categorical else None,
            min_value=column.min_value if values_read else None,
            max_value=column.max_value if values_read else None,
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
    columns: list[TabularColumnDescription] = Field(default_factory=list)
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

    columns: list[TabularColumnDescription] = Field(default_factory=list)


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
    markdown: str | None = None
    tables: list[TabularTableSchema] = Field(default_factory=list)
    source_tag: Optional[str] = None


class TabularQueryRequest(BaseModel):
    """
    One read-only DuckDB SELECT over authorized document tables.

    sql uses discovered table aliases; dataset_uids scopes exact document UUIDs.
    If omitted, SQL may reference any table in the active authorized scope; only
    referenced tables are mounted. An explicit empty list selects nothing. The query
    must read at least one table and respect the server's dataset limit. The trusted
    document scope is supplied by the runtime outside tool arguments. max_rows caps
    the returned preview; compute totals and statistics in SQL.
    """

    model_config = ConfigDict(extra="forbid")

    sql: str = Field(
        ...,
        min_length=1,
        description="One read-only DuckDB SELECT/WITH using exact tables[].query_alias values from describe_tabular_documents. These aliases are SQL table names, not document UUIDs or filenames. Must reference an authorized dataset; SELECT 1, writes and external reads are refused.",
    )
    dataset_uids: Optional[list[str]] = Field(
        default=None,
        max_length=1000,
        description="Document UUIDs copied exactly from authorized discovery, not filenames, SQL aliases or shortened identifiers. Omitted/null uses the authorized scope; [] selects nothing and query/search returns 400. Every requested UUID must be in scope; a workbook UUID selects all its tables.",
    )
    max_rows: Optional[int] = Field(
        default=None,
        ge=1,
        description="Requested result-row limit; omitted/null uses configured default_max_rows. Clamped to configured max_rows, not rejected when larger. No pagination; the response says when rows were cut. For totals or statistics, aggregate in SQL rather than counting this preview.",
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
    sql_query: str = Field(description="Validated SQL before the server adds its outer result-row LIMIT.")
    rows: list[dict] = Field(default_factory=list, description="JSON objects keyed by selected SQL columns; values depend on the query. At most row_limit rows.")
    truncated: bool = Field(default=False, description="True when the query produced more rows than row_limit: rows is partial, so compute counts and totals with SQL aggregates.")
    row_limit: int | None = Field(default=None, description="Result-row limit applied to this query.")
    error: Optional[str] = Field(default=None, description="Null on this mounted success path; failures use HTTP error statuses, not a success response containing an error.")
    message: str | None = Field(
        default=None,
        description="Explicit success explanation when the query returned zero rows (not an error or a claim that the whole document has no relevant information) or when the result is truncated.",
    )
    dataset_uids: list[str] = Field(default_factory=list, description="Document UUIDs of the mounted tables. A workbook UUID may appear more than once.")
    query_aliases: list[str] = Field(default_factory=list, description="Exact aliases of the mounted tables used by the query.")


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

    model_config = ConfigDict(extra="forbid")

    keyword: str = Field(
        ...,
        min_length=1,
        description="Precise word or expression of at least two characters after trimming (400 otherwise), nonempty once normalized. Case/accent/whitespace-insensitive substring matching, including numeric columns. Use after document description; generic terms match too many tables to locate a value.",
    )
    dataset_uids: Optional[list[str]] = Field(
        default=None,
        max_length=1000,
        description="Document UUIDs copied exactly from authorized discovery, not filenames, SQL aliases or shortened identifiers. Omitted/null uses the authorized scope; [] selects nothing and query/search returns 400. Every requested UUID must be in scope; a workbook UUID selects all its tables.",
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
      targeted `query_tabular_documents`.

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
