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
from pydantic import BaseModel
from fred_core import BaseModelWithId

from app.common.document_structures import DocumentMetadata


class TagType(Enum):
    """Enum representing the type of tag."""

    DOCUMENT = "document"  # For tags associated with documents
    PROMPT = "prompt"  # For tags associated with prompts


class TagCreate(BaseModel):
    """
    Data model for creating a new tag.
    Attributes:
        name (str): The name of the tag.
        description (str | None): Optional description of the tag.
        type (TagType): The type of the tag, e.g., DOCUMENT or PROMPT.
        item_ids (list[str]): List of item IDs associated with the tag. These are prompt or metata IDs.
    """

    name: str
    description: str | None = None
    type: TagType
    item_ids: list[str] = []


class TagUpdate(BaseModel):
    name: str
    description: str | None = None
    type: TagType
    item_ids: list[str] = []


# Saved data to represent a tag
class Tag(BaseModelWithId):
    created_at: datetime
    updated_at: datetime
    owner_id: str

    name: str
    description: str | None = None
    type: TagType


# Tag with associated document IDs coming from document metadata store
class TagWithItemsId(Tag, BaseModel):
    item_ids: list[str]

    @classmethod
    def from_tag(cls, tag: Tag, item_ids: list[str]) -> "TagWithItemsId":
        return cls(**tag.model_dump(), item_ids=item_ids)


# Tag with associated full document coming from document metadata store
class TagWithDocuments(Tag):
    documents: list[DocumentMetadata]

    @classmethod
    def from_tag(cls, tag: Tag, documents: list[DocumentMetadata]) -> "TagWithDocuments":
        return cls(**tag.model_dump(), documents=documents)
