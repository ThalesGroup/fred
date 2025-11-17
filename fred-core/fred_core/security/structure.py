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
    groups: list[str] = []


class M2MSecurity(BaseModel):
    """Configuration for machine-to-machine authentication."""

    enabled: bool = True
    realm_url: AnyUrl
    client_id: str
    audience: str | None = None
    secret_env_var: str = "M2M_CLIENT_SECRET"


class UserSecurity(BaseModel):
    """Configuration for user authentication."""

    enabled: bool = True
    realm_url: AnyUrl
    client_id: str


class RebacBaseConfig(BaseModel):
    enabled: bool = Field(
        default=True,
        description="To disable ReBAC checks (do not disable in production). If OIDC (UserSecurity and M2MSecurity) ReBAC check will be disabled even if this is true.",
    )


class SpiceDbRebacConfig(RebacBaseConfig):
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


class OpenFgaRebacConfig(RebacBaseConfig):
    """Configuration for an OpenFGA-backed relationship engine."""

    type: Literal["openfga"] = "openfga"
    api_url: AnyHttpUrl = Field(
        ...,
        description="Base URL for the OpenFGA HTTP API (e.g. https://fga.example.com)",
    )
    store_name: str = Field(
        default="fred", description="Name of the OpenFGA store to use"
    )
    authorization_model_id: str | None = Field(
        default=None,
        description="Optional authorization model ID to use for read operations",
    )
    create_store_if_needed: bool = Field(
        default=True,
        description="Create the OpenFGA store if it does not already exist",
    )
    sync_schema_on_init: bool = Field(
        default=True,
        description="Synchronize the authorization model when creating the engine",
    )
    token_env_var: str = Field(
        default="OPENFGA_API_TOKEN",
        description="Environment variable that stores the OpenFGA API token",
    )
    timeout_millisec: int | None = Field(
        default=None,
        description="Optional timeout in milliseconds for OpenFGA API requests",
    )
    headers: dict[str, str] | None = Field(
        default=None,
        description="Static HTTP headers to send with each OpenFGA API request",
    )


RebacConfiguration = Annotated[
    Union[SpiceDbRebacConfig, OpenFgaRebacConfig], Field(discriminator="type")
]


class SecurityConfiguration(BaseModel):
    m2m: M2MSecurity
    user: UserSecurity
    authorized_origins: List[AnyHttpUrl] = []
    rebac: RebacConfiguration | None = None
