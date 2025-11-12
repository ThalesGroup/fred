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

from fred_core import BaseModelWithId, RelationType, Resource, TagPermission
from pydantic import BaseModel, Field, field_validator

from knowledge_flow_backend.features.groups.groups_structures import GroupSummary
from knowledge_flow_backend.features.resources.structures import ResourceKind
from knowledge_flow_backend.features.users.users_structures import UserSummary

VALID_RESOURCE_KIND_IN_TAG = {}


class TagType(str, Enum):
    DOCUMENT = "document"
    PROMPT = ResourceKind.PROMPT.value
    TEMPLATE = ResourceKind.TEMPLATE.value
    CHAT_CONTEXT = ResourceKind.CHAT_CONTEXT.value

    def to_resource_kind(self):
        """Convert TagType to ResourceKind. Can raise a ValueError if TagType is not a valid ResourceKind"""
        return ResourceKind(self.value)


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
    """

    name: str
    path: Optional[str] = None
    description: Optional[str] = None
    type: TagType

    @field_validator("path")
    @classmethod
    def _validate_and_normalize_path(cls, v: Optional[str]) -> Optional[str]:
        v = _normalize_path(v)
        if v is None:
            return None
        # simple character policy; relax/tighten as needed
        for seg in v.split("/"):
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
    GROUP = Resource.GROUP.value

    def to_resource(self) -> Resource:
        return Resource(self.value)


class TagShareRequest(BaseModel):
    target_id: str
    target_type: ShareTargetResource
    relation: UserTagRelation


class TagPermissionsResponse(BaseModel):
    permissions: list[TagPermission]


class TagMemberUser(BaseModel):
    type: Literal["user"] = "user"
    relation: UserTagRelation
    user: UserSummary


class TagMemberGroup(BaseModel):
    type: Literal["group"] = "group"
    relation: UserTagRelation
    group: GroupSummary


class TagMembersResponse(BaseModel):
    users: list[TagMemberUser] = Field(default_factory=list)
    groups: list[TagMemberGroup] = Field(default_factory=list)
