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
from typing import Literal, Optional

from fred_core import RelationType, Resource, TagPermission
from fred_core.common import BaseModelWithId
from pydantic import BaseModel, Field, field_validator

from knowledge_flow_backend.features.resources.structures import ResourceKind
from knowledge_flow_backend.features.users.users_structures import UserSummary


class TagType(str, Enum):
    DOCUMENT = "document"
    PROMPT = ResourceKind.PROMPT.value
    TEMPLATE = ResourceKind.TEMPLATE.value
    CHAT_CONTEXT = ResourceKind.CHAT_CONTEXT.value

    def to_resource_kind(self):
        """Convert TagType to ResourceKind. Can raise a ValueError if TagType is not a valid ResourceKind"""
        return ResourceKind(self.value)


# Ceiling on the depth of a tag's FULL path (parent path + its own name).
# Guards the folder drag-and-drop mirroring (#2355): a dropped directory tree
# creates one tag per subdirectory, so an unbounded drop could nest tags
# arbitrarily deep. The frontend pre-filters against the same limit.
#
# 15 is bounded by ReBAC, not taste: every nested tag carries a PARENT tuple
# and the OpenFGA schema inherits permissions through that chain (`read from
# parent`, schema.fga), so a check on a depth-N tag resolves up to N hops —
# against OpenFGA's default 25-hop resolution limit, which the chain's other
# branches (owner/team_member) also draw from. Raising this materially means
# retuning OpenFGA (OPENFGA_RESOLVE_NODE_LIMIT) and re-checking the btree
# index on tag.path (~2.7KB max indexed value).
MAX_TAG_PATH_DEPTH = 15


def _normalize_path(p: Optional[str]) -> Optional[str]:
    if p is None:
        return None
    # strip spaces around segments, remove duplicate slashes
    parts = [seg.strip() for seg in p.split("/") if seg.strip()]
    return "/".join(parts) or None


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

    @field_validator("path")
    @classmethod
    def _validate_and_normalize_path(cls, v: Optional[str]) -> Optional[str]:
        v = _normalize_path(v)
        if v is None:
            return None
        segments = v.split("/")
        # `path` is the PARENT chain; the tag's own name adds one more level.
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

    @property
    def full_path(self) -> str:
        """Canonical hierarchical identifier (used for uniqueness & permissions)."""
        return f"{self.path}/{self.name}" if self.path else self.name


class TagWithItemsId(Tag):
    item_ids: list[str]

    @classmethod
    def from_tag(cls, tag: Tag, item_ids: list[str]) -> "TagWithItemsId":
        return cls(**tag.model_dump(), item_ids=item_ids)


class TagWithPermissions(TagWithItemsId):
    """Tag with user-specific permissions included."""

    permissions: list[TagPermission] = Field(default_factory=list)

    @classmethod
    def from_tag_with_items(cls, tag: TagWithItemsId, permissions: list[TagPermission]) -> "TagWithPermissions":
        return cls(**tag.model_dump(), permissions=permissions)


# Subset of RelationType for user-tag relations
class UserTagRelation(str, Enum):
    OWNER = RelationType.OWNER.value
    EDITOR = RelationType.EDITOR.value
    VIEWER = RelationType.VIEWER.value

    def to_relation(self) -> RelationType:
        return RelationType(self.value)


# Subset of valid Resource you can share a tag with
class ShareTargetResource(str, Enum):
    USER = Resource.USER.value

    def to_resource(self) -> Resource:
        return Resource(self.value)


class TagShareRequest(BaseModel):
    target_id: str
    target_type: ShareTargetResource
    relation: UserTagRelation


class TagMemberUser(BaseModel):
    type: Literal["user"] = "user"
    relation: UserTagRelation
    user: UserSummary


class TagMembersResponse(BaseModel):
    users: list[TagMemberUser] = Field(default_factory=list)


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
