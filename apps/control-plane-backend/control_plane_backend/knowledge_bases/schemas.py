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

from datetime import datetime
from typing import Any

from fred_core import PREFIX_PATTERN
from fred_sdk.contracts.models import FieldSpec
from fred_core.scheduler import Schedule
from pydantic import BaseModel, Field


class KnowledgeBasePublicationRequest(BaseModel):
    """What an image publishes about itself at deployment time.

    `prefix` is declared, never derived: only the image knows how much of its
    own name it claims — `fred` or `fred.samples` are both plausible readings
    of `fred.samples.local-folder`.
    """

    prefix: str = Field(min_length=1, max_length=256, pattern=PREFIX_PATTERN)
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    configuration_fields: list[FieldSpec] = Field(default_factory=list)


class KnowledgeBasePublicationResult(BaseModel):
    id: str
    prefix: str
    version: str


class KnowledgeBaseInstanceCreate(BaseModel):
    """Creating a folder that fills itself.

    Reached through folder creation, not through a Knowledge Base screen: the
    team names a folder and says what synchronizes it, and that one gesture is
    what creates the library, the instance, the pod's grant over it and its
    cadence.
    """

    definition_id: str = Field(min_length=1)
    team_id: str = Field(min_length=1)
    folder_name: str = Field(min_length=1, max_length=255)
    schedule: Schedule
    suspended: bool = False
    configuration: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBaseInstanceSummary(BaseModel):
    """One synchronized folder, as a team sees it.

    `configuration` carries no secret-declared value: a display read never
    hands one back, and leaving such a field empty on submit keeps what is
    stored.
    """

    id: str
    definition_id: str
    definition_name: str
    team_id: str
    library_id: str
    library_name: str
    schedule: Schedule
    suspended: bool
    configuration: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseDefinitionChoice(BaseModel):
    """One definition a team may synchronize a folder from.

    What a folder-creation form needs to offer the choice, and nothing else:
    the fields to fill in are fetched only once one is chosen.
    """

    definition_id: str
    name: str
    description: str = ""


class KnowledgeBaseInstanceFields(BaseModel):
    """The fields an instance form renders for the author's own configuration.

    Only the author's: Fred stores these values, hands them back at run time,
    and never reads them. What Fred owns — the schedule, and whether the
    instance is suspended — is typed on the instance schemas above, so nothing
    generic renders it and no key has to travel beside these.
    """

    configuration_fields: list[FieldSpec] = Field(default_factory=list)
