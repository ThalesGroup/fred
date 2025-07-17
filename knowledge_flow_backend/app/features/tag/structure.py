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


class Tag(BaseModelWithId):
    created_at: datetime
    updated_at: datetime
    owner_id: str

    name: str
    description: str | None = None
    type: TagType
    document_ids: list[str] = []
