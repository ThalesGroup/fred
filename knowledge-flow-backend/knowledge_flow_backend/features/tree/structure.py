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

from typing import List, Optional

from fred_core.common import OwnerFilter
from pydantic import BaseModel, Field


class DocumentTreeRequest(BaseModel):
    working_directory: Optional[str] = Field(
        default=None,
        description="Folder path prefix to start from, e.g. 'Sales/HR'. None lists from the root.",
    )
    tag_ids: Optional[List[str]] = Field(
        default=None,
        description="Restrict the listing to these folder tag ids (and their descendants), when set.",
    )
    owner_filter: Optional[OwnerFilter] = Field(
        default=None,
        description=(
            "Restrict the listing by ownership. None lists every folder the user "
            "can read (all their teams plus personal); PERSONAL restricts to the "
            "user's personal folders; TEAM restricts to a single team (requires "
            "team_id)."
        ),
    )
    team_id: Optional[str] = Field(
        default=None,
        description="Team whose folders to list. Required when owner_filter is TEAM.",
    )
    max_chars: int = Field(
        default=6000,
        ge=500,
        le=20_000,
        description="Render budget for the returned tree text. Oversized trees are pruned, deepest branches first.",
    )


class DocumentTreeResponse(BaseModel):
    tree: str
    truncated: bool = Field(description="True if any branch was pruned or items were omitted to fit max_chars.")
