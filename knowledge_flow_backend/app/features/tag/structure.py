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

from app.common.structures import DocumentMetadata


class TagType(Enum):
    LIBRARY = "library"


class TagCreate(BaseModel):
    name: str
    description: str | None = None
    type: TagType
    document_ids: list[str] = []


class TagUpdate(BaseModel):
    name: str
    description: str | None = None
    type: TagType
    document_ids: list[str] = []

# Saved data to represent a tag
class Tag(BaseModelWithId):
    created_at: datetime
    updated_at: datetime
    owner_id: str

    name: str
    description: str | None = None
    type: TagType

# Tag with associated document IDs coming from document metadata store
class TagWithDocumentsId(Tag, BaseModel):
    document_ids: list[str]

    @classmethod
    def from_tag(cls, tag: Tag, document_ids: list[str]) -> "TagWithDocumentsId":
        return cls(**tag.model_dump(), document_ids=document_ids)



# Tag with associated full document coming from document metadata store
class TagWithDocuments(Tag):
    documents: list[DocumentMetadata]

    @classmethod
    def from_tag(cls, tag: Tag, documents: list[DocumentMetadata]) -> "TagWithDocuments":
        return cls(**tag.model_dump(), documents=documents)
