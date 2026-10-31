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

"""Weaver admission for every pod route using the common user dependencies."""

from fastapi import Depends, FastAPI, HTTPException, Request
from fred_core.security import oidc
from fred_core.security.delegation import AssertedUser
from fred_core.security.structure import (
    KeycloakUser,
    is_service_agent,
)
from sqlalchemy import text

from fred_runtime.app.context import PodApplicationContext
from fred_runtime.app.dependencies import get_pod_container


async def _require_accepted(
    request: Request, subject: KeycloakUser | AssertedUser
) -> None:
    """Read Rust onboarding::require_accepted's facts using its canonical subject.

    OIDC subjects are already mapped by decode_jwt as in Rust auth.rs. Trusted
    delegated workloads must name that canonical person, never their own UID.
    This checks consent only; it does not implement Rust's future run resolver.
    """
    container = get_pod_container(request)
    version = container.configuration.app.gcu_version
    if version is None:
        return
    engine = container.get_sql_engine()
    if engine is None:
        raise RuntimeError("Weaver terms require initialized SQL storage")
    try:
        async with engine.connect() as connection:
            accepted = await connection.scalar(
                text(
                    "select exists(select 1 from terms_acceptance "
                    "where user_id = :uid and version = :version)"
                ),
                {"uid": subject.uid, "version": version},
            )
    except Exception:
        raise HTTPException(503, "terms_acceptance_unavailable") from None
    if accepted is not True:
        raise HTTPException(403, "user_not_accept_gcu")


async def current_user(
    request: Request,
    subject: KeycloakUser | AssertedUser = Depends(oidc.authenticate_request),
) -> KeycloakUser | AssertedUser:
    await _require_accepted(request, subject)
    return subject


async def current_user_or_service(
    request: Request,
    subject: KeycloakUser | AssertedUser = Depends(oidc.authenticate_request),
) -> KeycloakUser | AssertedUser:
    # This exception belongs only to routes explicitly accepting a service.
    # AssertedUser carries no roles; the effective person must accept terms.
    if not is_service_agent(subject):
        await _require_accepted(request, subject)
    return subject


def install_admission(app: FastAPI) -> None:
    """Replace all common pod admission dependencies, including nested consumers.

    JWT and delegation verification stay shared with other backends. The pod has
    no Swift directory snapshot, suspension hook or global filtering dependency.
    """
    app.dependency_overrides.update(
        {
            oidc.get_current_user: current_user,
            oidc.get_current_user_or_service: current_user_or_service,
            oidc.get_current_user_without_gcu: oidc.authenticate_request,
            oidc.get_current_user_before_gcu: oidc.authenticate_request,
        }
    )


async def prepare_authorization(
    container: PodApplicationContext,
) -> None:
    """Validate identity and shared SQL before exposing the pod."""
    security = container.configuration.security
    if security is None or security.profile != "c3":
        raise ValueError("Weaver agent pods require security.profile='c3'")
    oidc.configure_token_security(security)
    oidc.initialize_user_security(security.user)
    if not (security.user.audience or security.user.client_id).strip():
        raise ValueError("Weaver agent pods require a JWT audience")
    await container.initialize_sql()
    sql_engine = container.get_sql_engine()
    if sql_engine is None or sql_engine.dialect.name != "postgresql":
        raise ValueError("Weaver authorization requires shared PostgreSQL")
