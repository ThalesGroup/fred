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

import logging
import os
import secrets
from pathlib import Path

from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    RebacReference,
    Relation,
    RelationType,
    Resource,
)

from control_plane_backend.bootstrap.dependencies import BootstrapServiceDependencies
from control_plane_backend.bootstrap.schemas import (
    BootstrapAlreadyCompletedError,
    BootstrapAuthDisabledError,
    BootstrapPlatformAdminRequest,
    BootstrapPlatformAdminResponse,
    BootstrapRebacDisabledError,
    BootstrapTokenInvalidError,
)
from control_plane_backend.config.models import Configuration

logger = logging.getLogger(__name__)

# Matches BootstrapPlatformAdminRequest.token's min_length. A configured
# secret shorter than this (including empty/whitespace-only) is treated as
# "not configured", never as a comparable value — otherwise
# secrets.compare_digest("", "") (which returns True) could turn an empty
# secret file into a wildcard credential.
_MIN_TOKEN_LENGTH = 16


def _read_configured_token(configuration: Configuration) -> str | None:
    """Read the configured bootstrap secret, never generating or logging it.

    RFC Part 8 (§42.4): the secret always comes from outside Fred — an
    environment variable sourced from a Kubernetes Secret (checked first, the
    real-deployment path) or an explicitly operator-provided local file (dev
    stack only, e.g. `make bootstrap-token`). Fred never calls a random-token
    generator and never writes this value to a log line, in any environment.

    A value shorter than `_MIN_TOKEN_LENGTH` (including empty or
    whitespace-only) is treated as unconfigured rather than returned as-is —
    see the module-level comment on `_MIN_TOKEN_LENGTH`.

    Fail closed, no fallback: once `bootstrap_token_env_var` is configured,
    it is the only source consulted — `bootstrap_token_file` is never read,
    even if the named env var is missing, empty, or too short.
    """
    env_var = configuration.app.bootstrap_token_env_var
    if env_var:
        value = os.getenv(env_var)
        if value:
            value = value.strip()
            if len(value) >= _MIN_TOKEN_LENGTH:
                return value
        return None

    file_path = configuration.app.bootstrap_token_file
    if file_path and Path(file_path).exists():
        value = Path(file_path).read_text().strip()
        if len(value) >= _MIN_TOKEN_LENGTH:
            return value

    return None


async def bootstrap_platform_admin(
    user: KeycloakUser,
    request: BootstrapPlatformAdminRequest,
    deps: BootstrapServiceDependencies,
) -> BootstrapPlatformAdminResponse:
    """
    Grant `platform_admin` to the calling identity, once, on a fresh deployment.

    Why this function exists:
    - closes RFC Part 8's root-bootstrap problem without ever declaring a
      Keycloak `sub` in deployment config, and without a live-derived guard
      that a later admin removal could silently reopen

    Safety properties (do not relax — RFC Part 8 §42):
    - two independent proofs: a valid Keycloak JWT (`user`, already validated
      by `get_current_user`) and the deploy-time secret (`request.token`).
      Neither alone is sufficient.
    - self-promotion only: the grant always targets `user.uid`. There is no
      `identifier` field — this endpoint cannot promote a third party under
      any input.
    - durable completion, not a live re-derived check: guarded by
      `PlatformBootstrapStore`, a persisted marker, never by counting current
      `platform_admin` tuples. Removing every `platform_admin` later must not
      reopen this endpoint.
    - write order: the OpenFGA tuple is written *before* the durable marker,
      under the same Postgres advisory lock `rescue_team_admin` uses for its
      own check-then-write race. `add_relation` is idempotent
      (`on_duplicate_writes=IGNORE`) — so if the process
      crashes or OpenFGA fails before the marker is written, nothing is lost:
      a retry safely re-applies the same tuple and then closes the marker.
      The only residual window is narrower and non-critical: a second
      distinct secret-holder racing that exact gap could also be granted
      `platform_admin` for themselves — still self-promotion only, never a
      third party, and vastly preferable to the prior design's permanent
      lockout on any transient OpenFGA failure.
    - ReBAC must be enabled: with it disabled, `add_relation` is a silent
      no-op (`NoopRebacEngine`) — refused before the marker is written, or
      bootstrap would burn its one-time completion with no admin granted.
    - authentication must be real: with it disabled, `get_current_user`
      returns a mock identity with no validation — refused before the ReBAC
      guard, or the JWT "proof" the RFC requires would be a rubber stamp,
      leaving the deploy secret as the only real credential.

    How to use it:
    - call from `POST /bootstrap/platform-admin`, which requires
      `get_current_user` (JWT mandatory, unlike a normal "public" endpoint)

    Example:
    - `response = await bootstrap_platform_admin(user, request, deps)`
    """
    configured_token = _read_configured_token(deps.configuration)
    if configured_token is None or not secrets.compare_digest(
        configured_token, request.token
    ):
        raise BootstrapTokenInvalidError()

    if not deps.configuration.security.user.enabled:
        raise BootstrapAuthDisabledError()

    if not deps.rebac.enabled:
        raise BootstrapRebacDisabledError()

    store = deps.get_platform_bootstrap_store()
    if await store.is_completed():
        raise BootstrapAlreadyCompletedError()

    async with store.advisory_lock():
        if await store.is_completed():
            raise BootstrapAlreadyCompletedError()

        await deps.rebac.add_relation(
            Relation(
                subject=RebacReference(Resource.USER, user.uid),
                relation=RelationType.PLATFORM_ADMIN,
                resource=RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID),
            )
        )

        await store.mark_completed(completed_by=user.uid)

    logger.info(
        "[BOOTSTRAP] Granted platform_admin to %s (%s) via root bootstrap",
        user.uid,
        user.username,
    )
    return BootstrapPlatformAdminResponse(user_id=user.uid, username=user.username)
