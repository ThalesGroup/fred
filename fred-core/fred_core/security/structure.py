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

from typing import Annotated, List, Literal, Union

from pydantic import AnyHttpUrl, AnyUrl, BaseModel, Field


class KeycloakUser(BaseModel):
    """Represents an authenticated Keycloak user."""

    uid: str
    username: str
    roles: list[str]
    email: str | None = None


class M2MSecurity(BaseModel):
    """Configuration for machine-to-machine authentication."""

    enabled: bool = True
    realm_url: AnyUrl
    client_id: str
    audience: str | None = None
    # client_secret from ENV. WHY: never commit secrets to config files.


class UserSecurity(BaseModel):
    """Configuration for user authentication."""

    enabled: bool = True
    realm_url: AnyUrl
    client_id: str


class SpiceDbRebacConfig(BaseModel):
    """Configuration for a SpiceDB-backed relationship engine."""

    type: Literal["spicedb"] = "spicedb"
    endpoint: str = Field(
        ..., description="gRPC endpoint for the SpiceDB implementation (host:port)"
    )
    insecure: bool = Field(
        default=False, description="Use insecure connection instead of TLS"
    )
    sync_schema_on_init: bool = Field(
        default=True, description="Synchronize schema when building the engine"
    )
    token_env_var: str = Field(
        default="SPICEDB_TOKEN",
        description="Environment variable that stores the SpiceDB preshared key",
    )


RebacConfiguration = Annotated[Union[SpiceDbRebacConfig], Field(discriminator="type")]


class SecurityConfiguration(BaseModel):
    m2m: M2MSecurity
    user: UserSecurity
    authorized_origins: List[AnyHttpUrl] = []
    rebac: RebacConfiguration
