# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
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
from pydantic import BaseModel
from fred_core import BaseModelWithId

from app.features.tag.structure import Tag

class PromptCreate(BaseModel):
    name: str
    content: str
    description: str | None = None
    tags: list[str] = []


class PromptUpdate(BaseModel):
    name: str
    content: str
    description: str | None = None
    tags: list[str] = []


class Prompt(BaseModelWithId):
    name: str
    content: str
    description: str | None = None
    tags: list[str]
    owner_id: str
    created_at: datetime
    updated_at: datetime


class TagWithPrompts(Tag, BaseModel):
    prompts: list[Prompt]

    @classmethod
    def from_tag(cls, tag: Tag, prompts: list[Prompt]) -> "TagWithPrompts":
        return cls(**tag.model_dump(), prompts=prompts)


