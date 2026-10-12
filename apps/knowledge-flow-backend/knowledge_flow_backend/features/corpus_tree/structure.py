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

from typing import List, Literal, Optional

from fred_core.common import OwnerFilter
from pydantic import BaseModel, Field, model_validator


class DocumentTreeRequest(BaseModel):
    working_directory: Optional[str] = Field(
        default=None,
        description="Folder path prefix to start from, e.g. 'Sales/HR'. None lists from the root.",
    )
    tag_ids: Optional[List[str]] = Field(
        default=None,
        description="Restrict the listing to these folder tag ids (and their descendants), when set.",
    )
    document_uids: Optional[List[str]] = Field(
        default=None,
        description="Restrict the listing to these documents, dropping the folders left empty, when set.",
    )
    max_chars: int = Field(
        default=20_000,
        ge=500,
        le=60_000,
        description="Render budget for the returned tree text. Oversized trees are pruned, deepest branches first.",
    )
    name_filter: Optional[str] = Field(default=None, description="Literal case-insensitive substring of filename or title; requires limit.")
    sort_by: Literal["name", "added_to_kb"] = "name"
    sort_order: Literal["asc", "desc"] = "asc"
    limit: Optional[int] = Field(default=None, ge=1, le=100, description="Unique documents per page; omit for legacy tree browsing.")
    cursor: Optional[str] = Field(default=None, max_length=8192, description="Continuation from the same query and scope; requires limit.")

    @model_validator(mode="after")
    def validate_paging(self):
        if self.limit is None and self.model_fields_set.intersection({"name_filter", "sort_by", "sort_order", "cursor"}):
            raise ValueError("Paging arguments require limit")
        if self.name_filter is not None:
            self.name_filter = self.name_filter.strip() or None
        return self

    owner_filter: Optional[OwnerFilter] = Field(
        default=None,
        description="Filter by ownership: 'personal' for user-owned folders, 'team' for team-owned folders.",
    )
    team_id: Optional[str] = Field(
        default=None,
        description="Team ID, required when owner_filter is 'team'.",
    )


class DocumentTreeResponse(BaseModel):
    tree: str
    truncated: bool = Field(description="True if any branch was pruned or items were omitted to fit max_chars.")

    next_cursor: Optional[str] = None
    has_unknown_arrivals: Optional[bool] = None
