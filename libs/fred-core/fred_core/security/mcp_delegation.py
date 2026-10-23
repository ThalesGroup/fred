"""Verify an MCP request's delegated grant for the duration of that request."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Annotated, AsyncGenerator

from fastapi import HTTPException, Query, Request, Security

# Reached through the module, not bound at import: callers substitute the
# platform's authentication in tests, and a bound reference would ignore that.
from fred_core.security import oidc
from fred_core.security.delegation import (
    AssertedUser,
    DelegationGrant,
)
from fred_core.security.oidc import oauth2_scheme
from fred_core.security.structure import KeycloakUser

_verified_grant: ContextVar[DelegationGrant | None] = ContextVar(
    "fred_verified_mcp_grant", default=None
)


async def declare_delegation_parameters(
    person: Annotated[str | None, Query(max_length=256)] = None,
    run: Annotated[str | None, Query(max_length=256)] = None,
    agent: Annotated[str | None, Query(max_length=256)] = None,
) -> None:
    """Expose the canonical grant parameters on a route.

    The shared authentication dependency already reads and validates them; this
    makes that wire contract visible, which is also what lets a tool mount place
    them on the inner request.
    """


async def mcp_mount_auth(
    request: Request,
    token: Annotated[str, Security(oauth2_scheme)],
) -> AsyncGenerator[KeycloakUser | AssertedUser, None]:
    """Authenticate a tool mount and record who the call speaks for."""

    # The bearer scheme does not fail on a missing credential, so without this
    # an unauthenticated request reaches token decoding as an empty value.
    if not token:
        raise HTTPException(
            status_code=401,
            detail="No authentication token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # A grant rides the endpoint, never the enclosing body: that body is the
    # tool call itself, which the calling model influences.
    subject = await oidc.resolve_request_principal(
        request, oidc.decode_jwt(token), query_only=True
    )
    grant = (
        DelegationGrant(person=subject.uid, run=subject.run_id, agent=subject.agent_id)
        if isinstance(subject, AssertedUser)
        else None
    )
    reset: Token[DelegationGrant | None] = _verified_grant.set(grant)
    try:
        yield subject
    finally:
        _verified_grant.reset(reset)


def verified_grant() -> DelegationGrant | None:
    """The grant the current mounted call was verified to speak for."""

    return _verified_grant.get()
