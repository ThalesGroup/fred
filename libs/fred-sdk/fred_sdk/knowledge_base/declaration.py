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
The JSON-safe declaration an image publishes to Fred at deployment time.

Declarations only — identity, display metadata and configuration field
declarations. It never carries a configured value, a secret, or the handler.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from fred_sdk.contracts.models import FieldSpec
from fred_sdk.knowledge_base.knowledge_base import (
    KNOWLEDGE_BASE_ID_PATTERN,
    KnowledgeBase,
)


class KnowledgeBaseDeclaration(BaseModel):
    """Serializable projection of a `KnowledgeBase`, safe to publish."""

    id: str = Field(min_length=1, pattern=KNOWLEDGE_BASE_ID_PATTERN)
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    configuration_fields: list[FieldSpec] = Field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        """Return the compact JSON-safe body published to Control Plane.

        Defaults and unset values are dropped, so what crosses the wire is only
        what the author actually declared. It carries no client identity: Fred
        binds that from the token the publishing call presents.
        """
        return self.model_dump(mode="json", exclude_none=True, exclude_defaults=True)

    @classmethod
    def of(cls, knowledge_base: KnowledgeBase) -> "KnowledgeBaseDeclaration":
        """Project a live Knowledge Base into its publishable declaration.

        Field specs are deep-copied so a later edit to the live object cannot
        mutate a declaration already produced from it.
        """
        return cls(
            id=knowledge_base.id,
            version=knowledge_base.version,
            name=knowledge_base.name,
            description=knowledge_base.description,
            configuration_fields=[
                field.model_copy(deep=True)
                for field in knowledge_base.configuration_fields
            ],
        )
