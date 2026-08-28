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

"""Wire models for collaborative-team Fred applications."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApplicationSummary(BaseModel):
    """One installed application the selected team may currently use."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    name: str = Field(min_length=1, description="Generated i18n key")
    description: str = Field(min_length=1, description="Generated i18n key")
    icon: str = Field(min_length=1)
    host_api_version: Literal["1"]
    contract_digest: str = Field(min_length=1)


class ApplicationList(BaseModel):
    """Authorized application catalog for exactly one route team."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    catalog_revision: str = Field(min_length=1)
    items: list[ApplicationSummary]
