"""Carry a verified delegation grant across a tool mount into its route.

A tool server rebuilds the inner request from the declared arguments of the tool
being called, so a grant presented on the outer endpoint is visible to the mount
and absent from the route the tool resolves to. This module is that crossing.

Nothing here imports the tool-server package: the subclass that needs it lives
beside this module and is reachable through an optional extra.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Annotated, Any, AsyncIterator, Protocol, TypeVar

from fastapi import HTTPException, Query, Request, Security

# Reached through the module, not bound at import: callers substitute the
# platform's authentication in tests, and a bound reference would ignore that.
from fred_core.security import oidc
from fred_core.security.delegation import (
    GRANT_PARAM_AGENT,
    GRANT_PARAM_NAMES,
    GRANT_PARAM_PERSON,
    GRANT_PARAM_RUN,
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
) -> AsyncIterator[KeycloakUser | AssertedUser]:
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


def apply_verified_grant(arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Return the tool arguments a delegated inner call should carry.

    A grant among the arguments is model-controlled, so it is discarded before
    the one verified at the mount is applied. Without a verified grant the call
    names nobody rather than whoever the arguments claimed.
    """

    trusted = dict(arguments or {})
    for name in GRANT_PARAM_NAMES:
        trusted.pop(name, None)
    grant = _verified_grant.get()
    if grant is not None:
        trusted.update(
            {
                GRANT_PARAM_PERSON: grant.person,
                GRANT_PARAM_RUN: grant.run,
                GRANT_PARAM_AGENT: grant.agent,
            }
        )
    return trusted


class _SupportsMcpTools(Protocol):
    tools: Any


# Structural, so no tool-server import is needed, and generic so a caller keeps
# the concrete type it passed in.
_McpT = TypeVar("_McpT", bound=_SupportsMcpTools)


def strip_grant_tool_fields(mcp: _McpT) -> _McpT:
    """Hide the grant from the tool schemas offered to a model.

    The parameters stay on the route so the inner call can carry them, but a
    model able to set them could name any person.
    """

    for tool in mcp.tools:
        schema = tool.inputSchema
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for name in GRANT_PARAM_NAMES:
                properties.pop(name, None)
        required = schema.get("required")
        if isinstance(required, list):
            schema["required"] = [n for n in required if n not in GRANT_PARAM_NAMES]
    return mcp
