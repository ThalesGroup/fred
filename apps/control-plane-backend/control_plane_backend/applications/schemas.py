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
    """One registered application the selected team may currently use."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    # Registered applications are deployed independently of Fred, so their
    # labels travel as locale maps instead of keys into a Fred translation
    # bundle. "en" is always present and is the fallback.
    name: dict[str, str] = Field(min_length=1, description="Locale to display name")
    description: dict[str, str] = Field(
        min_length=1, description="Locale to description"
    )
    icon: str = Field(min_length=1)
    ui_prefix: str = Field(
        min_length=1,
        description=(
            "Browser-facing prefix the application frame loads. A path when the "
            "application UI is served from Fred's origin, an absolute http(s) "
            "URL when it is not."
        ),
    )


class ApplicationList(BaseModel):
    """Authorized application catalog for exactly one route team."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    items: list[ApplicationSummary]
