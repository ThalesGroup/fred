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

from __future__ import annotations

from pydantic import BaseModel, Field


class BootstrapPlatformAdminRequest(BaseModel):
    token: str = Field(
        ...,
        min_length=16,
        description="The one-time root-bootstrap secret.",
    )


class BootstrapPlatformAdminResponse(BaseModel):
    user_id: str = Field(
        ...,
        description=(
            "Keycloak sub granted platform_admin — always the calling JWT's own "
            "sub, never an arbitrary third party (RFC Part 8, §42.2)."
        ),
    )
    username: str


class BootstrapTokenInvalidError(Exception):
    """Raised when the bootstrap secret is missing, disabled, or does not match.

    Deliberately returned for both "feature not configured" and "wrong secret" —
    the caller should not be able to distinguish a disabled bootstrap endpoint
    from a wrong guess.
    """

    def __init__(self) -> None:
        super().__init__("Invalid or disabled bootstrap secret.")


class BootstrapAlreadyCompletedError(Exception):
    """Raised once the durable bootstrap-completed marker exists.

    RFC Part 8 (§42.3): this reads a durably persisted marker
    (`PlatformBootstrapStore`), not a live count of `platform_admin` tuples —
    removing every `platform_admin` later must not silently reopen this
    endpoint for anyone who still holds the secret. Permanently inert once
    set; never re-derived from current OpenFGA state.
    """

    def __init__(self) -> None:
        super().__init__(
            "Root bootstrap already completed — this endpoint is permanently "
            "disabled. Recovering from a lost platform_admin is a separate "
            "break-glass procedure, not a reopening of root bootstrap."
        )


class BootstrapRebacDisabledError(Exception):
    """Raised when ReBAC is disabled or unreachable in this deployment.

    Fail-closed, checked before the durable marker is written: with ReBAC
    disabled, `add_relation` is a silent no-op (`NoopRebacEngine`) — without
    this guard, bootstrap would burn its one-time completion marker while
    granting no one `platform_admin`, permanently, with no way to retry.
    """

    def __init__(self) -> None:
        super().__init__(
            "ReBAC is disabled in this deployment — root bootstrap cannot "
            "run without it. Enable ReBAC (and OIDC) before retrying."
        )


class BootstrapAuthDisabledError(Exception):
    """Raised when Keycloak/OIDC authentication is disabled in this deployment.

    Fail-closed: with authentication disabled, `get_current_user` returns a
    hardcoded mock identity with no real validation — the JWT "proof" the RFC
    requires (Part 8, §42.1: two independent proofs, neither alone
    sufficient) would degrade to a rubber stamp, leaving the deploy secret as
    the only real credential. Checked before the ReBAC-disabled guard, before
    any store access.
    """

    def __init__(self) -> None:
        super().__init__(
            "Authentication is disabled in this deployment — root bootstrap "
            "cannot run without real Keycloak/OIDC validation. Enable "
            "authentication before retrying."
        )
