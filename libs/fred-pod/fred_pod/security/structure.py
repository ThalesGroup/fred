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

import re
from dataclasses import dataclass
from typing import Annotated, List, Literal, Protocol, Union, runtime_checkable

from pydantic import AnyHttpUrl, AnyUrl, BaseModel, ConfigDict, Field, model_validator

from fred_pod.security.delegation import DelegationConfig


@runtime_checkable
class Principal(Protocol):
    """What a permission check needs from a caller, whichever kind it is.

    Satisfied structurally by `KeycloakUser` and by the asserted principal a
    delegation grant builds, so a receiver checks permissions the same way for both.
    """

    @property
    def uid(self) -> str: ...

    @property
    def roles(self) -> list[str]: ...

    @property
    def client_id(self) -> str | None: ...


class KeycloakUser(BaseModel):
    """Represents an authenticated Keycloak user."""

    uid: str
    username: str
    roles: list[str]
    email: str | None = None
    first_name: str | None = Field(default=None, exclude=True, repr=False)
    last_name: str | None = Field(default=None, exclude=True, repr=False)
    client_id: str | None = Field(
        default=None,
        description=(
            "The token's authorized party (`azp`, or `client_id` when `azp` is "
            "absent). Set for a client-credentials identity, so a caller can be "
            "checked against one exact client rather than a broad service role."
        ),
    )
    token_issuer: str | None = Field(default=None, exclude=True, repr=False)
    token_audiences: frozenset[str] = Field(
        default_factory=frozenset, exclude=True, repr=False
    )
    token_type: str | None = Field(default=None, exclude=True, repr=False)
    # Roles from the claim `security.delegation.caller_roles_claim` names, read
    # only from a verified token; never persisted, so never restored.
    caller_roles: frozenset[str] = Field(
        default_factory=frozenset, exclude=True, repr=False
    )
    # Whether the verified token bears Keycloak's service-account markers.
    service_account: bool = Field(default=False, exclude=True, repr=False)
    admission_attribute: str | list[str] | None = Field(
        default=None, exclude=True, repr=False
    )
    admission_issued_at: float | None = Field(default=None, exclude=True, repr=False)
    admission_expires_at: float | None = Field(default=None, exclude=True, repr=False)

    def __repr_args__(self):
        # Directly identifying data must never reach a log line, and an
        # f-string/log call interpolating this model (or anything containing
        # it) goes through repr — not model_dump() — so redacting here, not
        # only at each log call site, is what actually closes the leak
        # (docs/swift/platform/OBSERVABILITY-AND-AUDIT.md §7: "Directly
        # identifying | user email, full name | Nowhere"). Explicit `.email`
        # access for a genuine need (e.g. sending mail) is unaffected — this
        # only changes str()/repr().
        for name, value in super().__repr_args__():
            yield (name, "<redacted>" if name == "email" and value else value)


# Keycloak app role carried by backend service identities (agentic, knowledge-flow,
# control-plane, and the evaluation worker). Identity marker, not a ReBAC relation:
# nothing is stored in OpenFGA for it.
SERVICE_AGENT_ROLE = "service_agent"

# The `azp` a mock user carries when authentication is disabled, so routes
# gated on an exact client stay reachable in local development.
LOCAL_DEV_CLIENT_ID = "local-dev"


def is_service_agent(user: Principal) -> bool:
    """Return True when the caller is a service identity (holds ``service_agent``).

    Identity predicate on the JWT (reads ``user.roles``) — not a ReBAC check.
    Used by execution-authorization enforcement points (fred-runtime and the
    control-plane) to recognize the evaluation worker for team ``can_read``,
    scoped to the request ``team_id`` (RFC EVAL-AUTH, Solution A). No OpenFGA
    tuple links the service to a team. A principal asserted through a delegation
    grant carries no roles at all, so this is always False for one.
    """
    return SERVICE_AGENT_ROLE in (user.roles or [])


@dataclass(frozen=True, slots=True)
class PrincipalContext:
    """The bearer-authenticated caller and the person authorization acts on."""

    caller: KeycloakUser
    subject: Principal


class M2MSecurity(BaseModel):
    """Configuration for machine-to-machine authentication."""

    # A leftover key, such as the retired audience, must fail loudly, not be ignored.
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    realm_url: AnyUrl
    client_id: str
    provider: Literal["keycloak", "oidc"] = "keycloak"
    scope: str | None = None
    token_url: AnyHttpUrl | None = None
    secret_env_var: str = "M2M_CLIENT_SECRET"


class UserClaims(BaseModel):
    """Claim names used to construct an authenticated person's identity."""

    uid: str = "sub"
    username: str = "preferred_username"
    email: str = "email"
    given_name: str = "given_name"
    family_name: str = "family_name"


class UserSecurity(BaseModel):
    """Configuration for user authentication."""

    enabled: bool = True
    realm_url: AnyUrl = Field(description="Keycloak realm URL or OIDC issuer URL")
    client_id: str
    provider: Literal["keycloak", "oidc"] = "keycloak"
    audience: str | None = None
    scope: str | None = None
    jwks_url: AnyHttpUrl | None = None
    token_url: AnyHttpUrl | None = None
    roles_claim: list[str] | None = None
    claims: UserClaims = Field(default_factory=UserClaims)


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

    @model_validator(mode="before")
    @classmethod
    def _refuse_the_former_key(cls, data: object) -> object:
        # Ignored, the former key would leave the check off without a word.
        if isinstance(data, dict) and "standing_gate_enabled" in data:
            raise ValueError(
                "standing_gate_enabled was removed; using delegation enforces account status"
            )
        return data

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


class PlatformAccessConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    jwt_claim: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(
        default_factory=list, max_length=16
    )
    accepted_regex: str | None = Field(default=None, max_length=2048)
    supportLink: AnyHttpUrl | None = None

    @model_validator(mode="after")
    def validate_policy(self):
        if self.accepted_regex is not None:
            try:
                re.compile(self.accepted_regex)
            except re.error:
                raise ValueError(
                    "accepted_regex must be a valid regular expression"
                ) from None
        if self.supportLink is not None and (
            self.supportLink.scheme != "https"
            or self.supportLink.username is not None
            or self.supportLink.password is not None
        ):
            raise ValueError("supportLink must be an HTTPS URL")
        if self.enabled and (
            not self.jwt_claim
            or not all(key.strip() for key in self.jwt_claim)
            or not self.accepted_regex
            or self.supportLink is None
        ):
            raise ValueError(
                "Enabled platform access requires jwt_claim, accepted_regex and supportLink"
            )
        return self


class SecurityConfiguration(BaseModel):
    m2m: M2MSecurity
    user: UserSecurity
    user_directory: Literal["keycloak", "local"] = "keycloak"
    platform_access: PlatformAccessConfiguration = Field(
        default_factory=PlatformAccessConfiguration
    )
    delegation: DelegationConfig = Field(default_factory=DelegationConfig)
    authorized_origins: List[AnyHttpUrl] = []
    rebac: RebacConfiguration | None = None
    profile: Literal["c3"] | None = Field(
        default=None,
        description=(
            "Hardened security profile (RUNTIME-07). 'c3' forces strict JWT "
            "issuer/audience validation, forbids no-security/mock-admin, and "
            "requires OpenFGA ReBAC enabled (pod-side authorization, fail-closed) "
            "— failing startup otherwise. The control-plane issues no signed grant."
        ),
    )
