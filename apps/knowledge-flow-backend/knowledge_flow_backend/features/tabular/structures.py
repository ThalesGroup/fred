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

# -- Schema models --


class TabularColumnSchema(BaseModel):
    name: str
    dtype: DTypes


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


class TabularDatasetSchemaResponse(BaseModel):
    """
    Full schema description for one authorized dataset.

    Why this exists:
    - Schema inspection is now document-scoped instead of database/table-scoped.

    How to use:
    - Returned by `GET /tabular/datasets/{document_uid}/schema`.
    """

    document_uid: str
    document_name: str
    query_alias: str
    columns: list[TabularColumnSchema] = Field(default_factory=list)
    row_count: Optional[int] = None
    source_tag: Optional[str] = None
    generated_at: Optional[str] = None


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
