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

from sqlalchemy import Column, DateTime, String
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel

from knowledge_flow_backend.features.teams.team_id import TeamId


class TimestampMixin(SQLModel):
    """Mixin for automatic timestamp fields."""

    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        )
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        )
    )


class TeamMetadataBase(SQLModel):
    """Base model for team metadata fields (exposed in API)."""

    description: str | None = Field(default=None, nullable=True, max_length=180)
    is_private: bool = Field(default=True)


class TeamMetadata(TeamMetadataBase, TimestampMixin, table=True):
    """
    Additional metadata for a Keycloak group/team.
    Includes internal fields not exposed in API.
    """

    # id: Annotated[TeamId, PlainSerializer(lambda x: str(x), return_type=str)] = Field(sa_column=Column(String, primary_key=True))
    id: TeamId = Field(sa_column=Column(String, primary_key=True))
    banner_object_storage_key: str | None = Field(default=None, nullable=True, max_length=300)


class TeamMetadataUpdate(SQLModel):
    """Model for updating team metadata. All fields are optional."""

    description: str | None = None
    banner_object_storage_key: str | None = None
    is_private: bool | None = None
