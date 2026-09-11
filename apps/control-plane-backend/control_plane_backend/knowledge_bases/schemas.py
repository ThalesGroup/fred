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

"""Wire shapes for the Platform Admin Knowledge Base surface."""

from __future__ import annotations

from fred_sdk.contracts.models import FieldSpec
from pydantic import BaseModel, Field


class KnowledgeBasePublicationRequest(BaseModel):
    """What an image publishes about itself at deployment time."""

    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    configuration_fields: list[FieldSpec] = Field(default_factory=list)


class KnowledgeBasePublicationResult(BaseModel):
    provider_id: str
    definition_id: str
    version: str
