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

"""
The JSON-safe artifact an operator installs into a Fred deployment.

Declarations only — identity, display metadata and configuration field
declarations. It never carries a configured value, a secret, or the handler.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from fred_sdk.contracts.models import FieldSpec
from fred_sdk.knowledge_base.declaration import (
    KNOWLEDGE_BASE_ID_PATTERN,
    KnowledgeBase,
)


class KnowledgeBaseManifest(BaseModel):
    """Projection of a `KnowledgeBase` declaration, safe to serialize and ship."""

    id: str = Field(min_length=1, pattern=KNOWLEDGE_BASE_ID_PATTERN)
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    configuration_fields: list[FieldSpec] = Field(default_factory=list)

    @classmethod
    def from_declaration(cls, declaration: KnowledgeBase) -> "KnowledgeBaseManifest":
        """Project a live declaration into its installable artifact.

        Field specs are deep-copied so a later edit to the declaration cannot
        mutate an artifact already produced from it.
        """
        return cls(
            id=declaration.id,
            version=declaration.version,
            name=declaration.name,
            description=declaration.description,
            configuration_fields=[
                field.model_copy(deep=True)
                for field in declaration.configuration_fields
            ],
        )
