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

"""Delegated execution grant: the plain statement a workload sends about the
person, run and agent a call acts for. It is believed only when the workload's
own verified bearer carries the delegation caller role.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping

from fastapi import HTTPException
from fred_pod.security.delegation import DelegationConfig, GrantIdentifier
from pydantic import BaseModel, ValidationError
from starlette.requests import ClientDisconnect, Request

if TYPE_CHECKING:
    from fred_core.security.structure import KeycloakUser

from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.auth_metrics import DELEGATION
from fred_core.security.structure import is_service_agent

logger = logging.getLogger(__name__)

# Request parameter names shared by every caller and every receiver.
GRANT_PARAM_PERSON = "person"
GRANT_PARAM_RUN = "run"
GRANT_PARAM_AGENT = "agent"
GRANT_PARAM_NAMES = (GRANT_PARAM_PERSON, GRANT_PARAM_RUN, GRANT_PARAM_AGENT)

# A query pair carrying a grant value, wherever a URL is quoted inside text.
_GRANT_QUERY_VALUE = re.compile(
    r"(?<=[?&])(" + "|".join(GRANT_PARAM_NAMES) + r")=[^&\s'\"]*"
)

AUDIT_GRANT_ACCEPTED = "delegation.grant.accepted"
AUDIT_GRANT_REJECTED = "delegation.grant.rejected"


class DelegationGrant(BaseModel):
    """The three parameters as received; validated shape only, trust is decided elsewhere."""

    person: GrantIdentifier
    run: GrantIdentifier
    agent: GrantIdentifier


@dataclass(frozen=True, slots=True)
class AssertedUser:
    """A person a trusted workload speaks for, who presented no credential.

    Deliberately not a `KeycloakUser`: it carries no roles at all, so no
    service-role shortcut can ever fire for a person named by a caller.
    """

    uid: str
    client_id: str
    run_id: str
    agent_id: str

    @property
    def roles(self) -> list[str]:
        return []


@dataclass(frozen=True, slots=True)
class _Installed:
    config: DelegationConfig
    issuers: frozenset[str]
    user_clients: frozenset[str]


_installed = _Installed(DelegationConfig(), frozenset(), frozenset())

# The token types a workload's access token may declare; providers that do not
# label access tokens leave the claim out.
_ACCESS_TOKEN_TYPES = frozenset({"bearer", "at+jwt"})


def initialize_delegation(
    config: DelegationConfig,
    *,
    issuers: Iterable[str] = (),
    user_clients: Iterable[str] = (),
) -> None:
    """Install the delegation block read at startup. Off until a backend calls this.

    `issuers` are the addresses of the realm this receiver trusts; `user_clients`
    adds to the block's own list of clients people sign in through.
    """
    global _installed
    _installed = _Installed(
        config=config,
        issuers=frozenset(issuer.rstrip("/") for issuer in issuers if issuer),
        user_clients=frozenset(user_clients) | frozenset(config.user_clients),
    )
    logger.info(
        "[AUTH] Delegation initialized: act_for_people=%s accept_delegated_calls=%s "
        "caller_role=%s",
        config.act_for_people,
        config.accept_delegated_calls,
        config.caller_role,
    )


@contextmanager
def preserved_delegation() -> Iterator[None]:
    """Restore the delegation settings installed on entry when the block ends."""
    global _installed
    installed = _installed
    try:
        yield
    finally:
        _installed = installed


def get_delegation_config() -> DelegationConfig:
    return _installed.config


def is_user_client(client_id: str | None) -> bool:
    """True when `client_id` is a client people sign in through."""
    return client_id is not None and client_id in _installed.user_clients


def read_caller_roles(payload: Mapping[str, Any]) -> frozenset[str]:
    """The roles at the configured claim path of a verified token payload.

    Read whatever the switches: a backend that believes no grant must still
    recognise a delegation client, which holds the service role too.
    """
    config = get_delegation_config()
    value: Any = payload
    for key in config.roles_claim_path:
        value = value.get(key) if isinstance(value, Mapping) else None
    if not isinstance(value, list):
        return frozenset()
    return frozenset(role for role in value if isinstance(role, str) and role)


def bears_service_account_markers(
    payload: Mapping[str, Any], client_id: str | None
) -> bool:
    """True when a verified Keycloak token was issued to `client_id`'s own service account.

    Keycloak names that account service-account-<client> and adds the client id claim
    only to client-credentials tokens.
    """
    if not client_id:
        return False
    username = payload.get("preferred_username")
    named = payload.get("client_id", payload.get("clientId"))
    return (
        isinstance(username, str)
        and username.lower() == f"service-account-{client_id}".lower()
        and named == client_id
    )


def holds_caller_role(principal: Any) -> bool:
    """True when a verified bearer carries the delegation caller role.

    Independent of the switches, so a delegation client never takes the
    service-identity shortcuts. A principal asserted through a grant has no roles.
    """
    config = get_delegation_config()
    return bool(getattr(principal, "client_id", None)) and (
        config.caller_role in getattr(principal, "caller_roles", frozenset())
    )


def is_delegation_caller(caller: KeycloakUser) -> bool:
    """True when the verified bearer is a workload trusted to speak for a person.

    The role alone is not enough: the token must also be an access token from this
    realm, be addressed to the delegation audience, and not be issued to a client
    people sign in through.
    """
    config = get_delegation_config()
    token_type = caller.token_type
    return (
        config.accept_delegated_calls
        and holds_caller_role(caller)
        and (token_type is None or token_type.lower() in _ACCESS_TOKEN_TYPES)
        and (caller.token_issuer or "").rstrip("/") in _installed.issuers
        and config.audience in caller.token_audiences
        and not is_user_client(caller.client_id)
        and (caller.service_account or not config.service_accounts_only)
    )


def require_workload_caller(caller: KeycloakUser) -> None:
    """Require a verified workload trusted to delegate.

    This is the caller-only half of delegation authorization. Receivers use it
    where a decision belongs to the calling workload rather than to the person it
    names, such as a delegated model override.
    """
    if not is_delegation_caller(caller):
        raise HTTPException(status_code=403, detail="workload_caller_not_allowed")


async def resolve_delegated_principal(
    request: Request,
    caller: KeycloakUser,
    *,
    query_only: bool = False,
) -> AssertedUser | None:
    """Return the person the verified caller speaks for, or None for no subject.

    Called once the bearer is verified, so the only question left is whether it
    may speak for people and whether the parameters beside it are whole.
    """
    if not get_delegation_config().accept_delegated_calls:
        return None

    if not holds_caller_role(caller):
        await _refuse_a_grant_from_an_unbelieved_caller(
            request, caller, query_only=query_only
        )
        return None

    raw = await _read_grant_parameters(request, query_only=query_only)
    if raw is None:
        return None  # a trusted caller without parameters acts for nobody

    grant = _parse_grant(raw)
    if grant is None:
        DELEGATION.labels("rejected", "invalid_parameters").inc()
        emit_audit_log(
            AUDIT_GRANT_REJECTED,
            "warning",
            outcome="rejected",
            reason="invalid_parameters",
        )
        return None

    client_id = caller.client_id
    if client_id is None or not is_delegation_caller(caller):
        DELEGATION.labels("rejected", "caller_not_allowed").inc()
        emit_audit_log(
            AUDIT_GRANT_REJECTED,
            "warning",
            outcome="rejected",
            reason="caller_not_allowed",
        )
        raise HTTPException(status_code=403, detail="delegation_not_allowed")

    DELEGATION.labels("accepted", "grant_validated").inc()
    emit_audit_log(
        AUDIT_GRANT_ACCEPTED,
        "info",
        outcome="accepted",
        reason="grant_validated",
    )
    return AssertedUser(
        uid=grant.person,
        client_id=client_id,
        run_id=grant.run,
        agent_id=grant.agent,
    )


async def _refuse_a_grant_from_an_unbelieved_caller(
    request: Request, caller: KeycloakUser, *, query_only: bool
) -> None:
    """Refuse a whole grant offered by a caller that may not speak for anyone.

    Served as itself, a workload provisioned without the role would keep its
    service-identity shortcuts, so a service identity's body is read too, never
    a person's. The values stay out of the audit: they are the caller's own text.
    """
    offered = _present(request.query_params)
    if (
        len(offered) != len(GRANT_PARAM_NAMES)
        and not query_only
        and is_service_agent(caller)
    ):
        offered = _present(await _read_json_object(request) or {})
    if len(offered) != len(GRANT_PARAM_NAMES):
        return

    DELEGATION.labels("rejected", "caller_not_trusted").inc()
    emit_audit_log(
        AUDIT_GRANT_REJECTED,
        "warning",
        outcome="rejected",
        reason="caller_not_trusted",
    )
    raise HTTPException(status_code=403, detail="delegation_not_allowed")


def _parse_grant(raw: Mapping[str, Any]) -> DelegationGrant | None:
    try:
        return DelegationGrant.model_validate(dict(raw))
    except ValidationError:
        return None


def _present(source: Mapping[str, Any]) -> dict[str, Any]:
    return {name: source[name] for name in GRANT_PARAM_NAMES if name in source}


async def _read_grant_parameters(
    request: Request, *, query_only: bool = False
) -> dict[str, Any] | None:
    """Collect the parameters from one transport only — never merged across two.

    A partial set is returned as it stands so the attempt is refused and audited
    rather than completed from a second source.
    """
    from_query = _present(request.query_params)
    if len(from_query) == len(GRANT_PARAM_NAMES):
        return from_query

    if query_only:
        return from_query or None

    from_body = _present(await _read_json_object(request) or {})
    if len(from_body) == len(GRANT_PARAM_NAMES):
        return from_body

    return from_query or from_body or None


async def _read_json_object(request: Request) -> Mapping[str, Any] | None:
    """Top-level fields of a JSON body, or None.

    Anything nested — tool arguments above all — is not a grant, and any other
    media type is left untouched so uploads and streams are never buffered.
    """
    media_type = (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    )
    maintype, _, subtype = media_type.partition("/")
    if maintype != "application" or not (
        subtype == "json" or subtype.endswith("+json")
    ):
        return None

    try:
        # Starlette caches the body, and FastAPI has already read it for any
        # endpoint declaring one, so this never starves the endpoint's parsing.
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ClientDisconnect):
        return None  # the endpoint reports its own error on an unusable body

    return payload if isinstance(payload, dict) else None


def scrub_grant_text(text: str) -> str:
    """Drop the grant values from any URL quoted inside a string.

    For log lines and error text that repeat a request URL: the parameter names
    stay, so a reader still sees a grant was present, the values do not.
    """
    return _GRANT_QUERY_VALUE.sub(lambda match: f"{match.group(1)}=", text)


__all__ = [
    "AUDIT_GRANT_ACCEPTED",
    "AUDIT_GRANT_REJECTED",
    "GRANT_PARAM_AGENT",
    "GRANT_PARAM_NAMES",
    "GRANT_PARAM_PERSON",
    "GRANT_PARAM_RUN",
    "AssertedUser",
    "DelegationConfig",
    "DelegationGrant",
    "bears_service_account_markers",
    "get_delegation_config",
    "holds_caller_role",
    "initialize_delegation",
    "is_delegation_caller",
    "is_user_client",
    "preserved_delegation",
    "read_caller_roles",
    "require_workload_caller",
    "resolve_delegated_principal",
    "scrub_grant_text",
]
