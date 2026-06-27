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
        description="Optional authorization model ID to use for read operations. Will be overridden if sync_schema_on_init is True.",
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
        default=5000,
        description=(
            "Timeout in milliseconds for OpenFGA API requests. Defaults to 5000 so a "
            "stalled OpenFGA call fails fast with an error instead of hanging the request "
            "indefinitely (set to None only to explicitly disable the timeout)."
        ),
    )
    headers: dict[str, str] | None = Field(
        default=None,
        description="Static HTTP headers to send with each OpenFGA API request",
    )


RebacConfiguration = Annotated[Union[OpenFgaRebacConfig], Field(discriminator="type")]


class GrantSigningConfig(BaseModel):
    """
    ExecutionGrant signing/verification configuration (RUNTIME-07).

    Control-plane uses the SIGNING fields to sign each grant at prepare-execution;
    the runtime uses the VERIFICATION fields to verify autonomously (no callback).

    The primary, first-tested path is ``kind="local"`` (an RSA private key the
    control-plane mounts) + ``jwks_url`` pointing at the control-plane's own JWKS
    endpoint — this works fully offline (local Docker: Keycloak + SeaweedFS, or any
    on-prem deployment without GCP). ``kind="gcp"`` is the GKE keyless option.
    """

    enabled: bool = Field(
        default=False,
        description="When false, grants are not signed and signatures are not enforced.",
    )
    kind: Literal["local", "gcp"] = Field(
        default="local",
        description="Signer backend: 'local' (in-process RSA key) or 'gcp' (IAM signBlob).",
    )
    key_id: str = Field(
        default="cp-grant-key-1",
        description="Key identifier embedded in the grant for verifier key selection.",
    )

    # --- local signer (control-plane only) ---
    private_key_env_var: str = Field(
        default="FRED_GRANT_SIGNING_PRIVATE_KEY",
        description="Env var holding the PEM RSA private key (local signer).",
    )
    private_key_path: str | None = Field(
        default=None,
        description="Path to a mounted PEM RSA private key; takes precedence over the env var.",
    )

    # --- gcp signer (control-plane only) ---
    signing_service_account_email: str | None = Field(
        default=None,
        description="Service account used by IAM signBlob (kind='gcp', Workload Identity).",
    )

    # --- verification (runtime) ---
    jwks_url: str | None = Field(
        default=None,
        description="JWKS URL the runtime fetches to verify grant signatures.",
    )
    enforcement: Literal["observe", "enforce"] = Field(
        default="observe",
        description=(
            "Rollout mode at the runtime: 'observe' verifies and logs mismatches but "
            "still serves; 'enforce' rejects invalid/unsigned grants and runs from the "
            "grant alone (no resolution callback)."
        ),
    )


class SecurityConfiguration(BaseModel):
    m2m: M2MSecurity
    user: UserSecurity
    authorized_origins: List[AnyHttpUrl] = []
    rebac: RebacConfiguration | None = None
    grant_signing: GrantSigningConfig | None = None
