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
from fred_sdk.knowledge_base.schedule import DEFAULT_CADENCE, RunCadence
from pydantic import BaseModel, Field

from control_plane_backend.knowledge_bases.runs import RunState


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
    cadence: RunCadence = DEFAULT_CADENCE
    suspended: bool = False
    configuration: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBaseInstanceUpdate(BaseModel):
    """What a team may change: when it runs, and the author's own fields.

    Not the library and not the definition — a synchronized folder that changed
    either would be a different folder.
    """

    cadence: RunCadence
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
    cadence: RunCadence
    suspended: bool
    configuration: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseInstanceFields(BaseModel):
    """The two zones an instance form renders.

    `platform_fields` is Fred's own: it declares when the folder runs, and Fred
    acts on it. `configuration_fields` is the author's: Fred stores those
    values, hands them back at run time, and never reads them.
    """

    definition_id: str
    definition_name: str
    platform_fields: list[FieldSpec] = Field(default_factory=list)
    configuration_fields: list[FieldSpec] = Field(default_factory=list)


class KnowledgeBaseRunSummary(BaseModel):
    """One run, with the state the workflow engine reports for it."""

    run_id: str
    state: RunState
    started_at: datetime
