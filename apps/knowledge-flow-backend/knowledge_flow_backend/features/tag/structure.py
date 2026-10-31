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

from datetime import datetime
from enum import Enum
from typing import Optional

from fred_core.common import BaseModelWithId
from pydantic import BaseModel, Field, field_validator

from knowledge_flow_backend.features.resources.structures import ResourceKind


class TagType(str, Enum):
    DOCUMENT = "document"
    PROMPT = ResourceKind.PROMPT.value
    TEMPLATE = ResourceKind.TEMPLATE.value
    CHAT_CONTEXT = ResourceKind.CHAT_CONTEXT.value

    def to_resource_kind(self):
        """Convert TagType to ResourceKind. Can raise a ValueError if TagType is not a valid ResourceKind"""
        return ResourceKind(self.value)


MAX_TAG_PATH_DEPTH = 15


def _normalize_path(p: Optional[str]) -> Optional[str]:
    if p is None:
        return None
    # strip spaces around segments, remove duplicate slashes
    parts = [seg.strip() for seg in p.split("/") if seg.strip()]
    return "/".join(parts) or None


def _validate_name(v: str) -> str:
    """A tag NAME is a single path segment — never a path.

    The depth cap counts `path` segments + 1 for the name, and
    `TagService._compose_full_path` joins them with "/": a name carrying "/"
    would create several levels in one call, silently bypassing
    MAX_TAG_PATH_DEPTH (and the uniqueness scoping) — found live on #2355.
    """
    v = v.strip()
    if not v:
        raise ValueError("Name cannot be empty")
    if "/" in v or "\\" in v:
        raise ValueError("Name cannot contain '/' or '\\' — a tag name is a single folder level")
    return v


class TagCreate(BaseModel):
    """
    name: leaf segment (e.g. 'HR')
    path: optional parent path (e.g. 'Sales'); full path becomes 'Sales/HR'
    team_id: optional team ID. If provided, the tag is owned by the team instead of the user.
    """

    name: str
    path: Optional[str] = None
    description: Optional[str] = None
    type: TagType
    team_id: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _validate_single_segment_name(cls, v: str) -> str:
        return _validate_name(v)

    @field_validator("path")
    @classmethod
    def _validate_and_normalize_path(cls, v: Optional[str]) -> Optional[str]:
        v = _normalize_path(v)
        if v is None:
            return None
        segments = v.split("/")
        # `path` is the PARENT chain; the tag's own name adds exactly one more
        # level (names are validated single segments).
        if len(segments) + 1 > MAX_TAG_PATH_DEPTH:
            raise ValueError(f"Path too deep: at most {MAX_TAG_PATH_DEPTH} folder levels are allowed")
        # simple character policy; relax/tighten as needed
        for seg in segments:
            if not seg:
                raise ValueError("Path contains empty segment")
            if any(c in seg for c in "\\"):
                raise ValueError("Path contains forbidden character '\\'")
        return v


class TagUpdate(BaseModel):
    name: str
    path: Optional[str] = None
    description: Optional[str] = None
    type: TagType
    item_ids: list[str] = []

    @field_validator("item_ids")
    @classmethod
    def _no_none_ids(cls, v):
        return [i for i in v if i]

    @field_validator("name")
    @classmethod
    def _validate_single_segment_name(cls, v: str) -> str:
        return _validate_name(v)

    @field_validator("path")
    @classmethod
    def _validate_and_normalize_path(cls, v: Optional[str]) -> Optional[str]:
        return TagCreate._validate_and_normalize_path(v)  # reuse logic


class Tag(BaseModelWithId):
    created_at: datetime
    updated_at: datetime
    owner_id: str

    name: str  # leaf segment, e.g. 'HR'
    path: Optional[str] = None  # parent path, e.g. 'Sales'
    description: Optional[str] = None
    type: TagType

    # Where the system that synchronizes into this library last got to: a commit
    # sha, a cursor, a timestamp its own source understands. Fred stores it and
    # hands it back, and never reads meaning into it — that is what lets a pull
    # of a Git branch ask its own source what changed rather than keep a ledger.
    # Absent on every library nothing synchronizes into, and not part of
    # TagCreate/TagUpdate: it is recorded through its own endpoint, so a caller
    # never has to restate a folder's name or description to move its cursor.
    source_version: Optional[str] = None

    # Which machine fills this folder, as "<kind>:<id>". Present means a machine
    # writes here and people may not change what it holds; absent means people
    # do, which is every folder that predates this field. Only a service
    # identity can set it, and only on the folder a library starts at — anything
    # nested resolves its own state from that root, so the two cannot disagree.
    # Never parsed here: presence is the whole question.
    synchronized_by: Optional[str] = None

    @property
    def is_synchronized(self) -> bool:
        """True when a machine fills this folder, so people may not write in it."""
        return self.synchronized_by is not None

    @property
    def full_path(self) -> str:
        """Canonical hierarchical identifier (used for uniqueness & permissions)."""
        return f"{self.path}/{self.name}" if self.path else self.name


class TagWithItemsId(Tag):
    item_ids: list[str]

    @classmethod
    def from_tag(cls, tag: Tag, item_ids: list[str]) -> "TagWithItemsId":
        return cls(**tag.model_dump(), item_ids=item_ids)


class ResourceTypeStatsEntry(BaseModel):
    """One file-type bucket's count and total size, for the Resources dashboard usage
    cards (FRONT-09.I)."""

    bucket: str
    count: int
    size_bytes: int


class ResourceTypeStatsResponse(BaseModel):
    entries: list[ResourceTypeStatsEntry] = Field(default_factory=list)


class MissingTeamIdError(Exception):
    """Raised when owner_filter is 'team' but no team_id is provided."""
