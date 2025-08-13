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
from typing import List, Optional

from pydantic import BaseModel, Field
from fred_core import BaseModelWithId


class ResourceKind(str, Enum):
    PROMPT = "prompt"
    TEMPLATE = "template"


class ResourceUpdate(BaseModel):
    content: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    labels: Optional[List[str]] = None


class ResourceCreate(BaseModel):
    kind: ResourceKind
    content: str
    name: Optional[str] = None
    description: Optional[str] = None
    labels: Optional[List[str]] = None


class Resource(BaseModelWithId):
    id: str
    kind: ResourceKind
    version: str
    name: Optional[str] = None
    description: Optional[str] = None
    labels: Optional[List[str]] = None
    author: str
    created_at: datetime
    updated_at: datetime
    content: str = Field(..., description="Raw YAML text or other content")
    library_tags: List[str] = Field(..., description="List of tags associated with the resource")
