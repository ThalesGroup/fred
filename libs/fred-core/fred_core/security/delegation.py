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
own bearer names a client on the receiver's allow-list.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping

from fastapi import HTTPException
from fred_pod.security.delegation import (
    CallerPolicy,
    DelegationConfig,
    GrantIdentifier,
)
from pydantic import BaseModel, ValidationError
from starlette.requests import ClientDisconnect, Request

if TYPE_CHECKING:
    from fred_core.security.structure import KeycloakUser

from fred_core.logs.audit_log import emit_audit_log

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
    """A person an allow-listed workload speaks for, who presented no credential.

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


_delegation_config = DelegationConfig()
_delegation_issuer: str | None = None
_delegation_audience: str | None = None


def initialize_delegation(
    config: DelegationConfig,
    *,
    issuer: str | None = None,
    audience: str | None = None,
) -> None:
    """Install the delegation block read at startup. Off until a backend calls this."""
    global _delegation_audience, _delegation_config, _delegation_issuer
    _delegation_config = config
    _delegation_issuer = issuer.rstrip("/") if issuer else None
    _delegation_audience = audience
    logger.info(
        "[AUTH] Delegation acceptance initialized: enabled=%s allowed_callers=%d",
        config.enabled,
        len(config.allowed_callers),
    )


def get_delegation_config() -> DelegationConfig:
    return _delegation_config


def require_workload_caller(caller: KeycloakUser) -> CallerPolicy:
    """Require the configured verified workload identity.

    This is the caller-only half of delegation authorization. Receivers use it
    for surfaces, such as terminal lifecycle reporting, that must not resolve or
    authorize an asserted person.
    """

    config = get_delegation_config()
    policy = (
        config.policy_for(
            client_id=caller.client_id,
            subject=caller.uid,
        )
        if config.enabled and caller.client_id
        else None
    )
    if (
        policy is None
        or caller.token_type != "Bearer"  # nosec B105 - protocol metadata or synthetic fixture
        or _delegation_issuer is None
        or caller.token_issuer != _delegation_issuer
        or _delegation_audience is None
        or _delegation_audience not in caller.token_audiences
    ):
        raise HTTPException(status_code=403, detail="workload_caller_not_allowed")
    return policy


async def resolve_delegated_principal(
    request: Request,
    caller: KeycloakUser,
    *,
    query_only: bool = False,
) -> AssertedUser | None:
    """Return the person the verified caller speaks for, or None for no subject.

    Called once the bearer is verified, so the only question left is whether its
    client may speak for people and whether the parameters beside it are whole.
    """
    config = get_delegation_config()
    if not config.enabled:
        return None

    if not caller.client_id or not config.allows(caller.client_id):
        _audit_grant_from_an_unbelieved_caller(request, caller.client_id)
        return None

    raw = await _read_grant_parameters(request, query_only=query_only)
    if raw is None:
        return None  # an allow-listed caller without parameters acts for nobody

    grant = _parse_grant(raw)
    if grant is None:
        emit_audit_log(
            AUDIT_GRANT_REJECTED,
            "warning",
            outcome="rejected",
            reason="invalid_parameters",
        )
        return None

    try:
        require_workload_caller(caller)
    except HTTPException:
        emit_audit_log(
            AUDIT_GRANT_REJECTED,
            "warning",
            outcome="rejected",
            reason="caller_not_allowed",
        )
        raise HTTPException(status_code=403, detail="delegation_not_allowed")

    emit_audit_log(
        AUDIT_GRANT_ACCEPTED,
        "info",
        outcome="accepted",
        reason="grant_validated",
    )
    return AssertedUser(
        uid=grant.person,
        client_id=caller.client_id,
        run_id=grant.run,
        agent_id=grant.agent,
    )


def _audit_grant_from_an_unbelieved_caller(
    request: Request, caller_client_id: str | None
) -> None:
    """Record that a whole grant was offered by a caller that may not speak for anyone.

    Only the query is inspected: reading a body for every caller would parse the
    JSON of ordinary traffic twice, and a partial set there is noise, not an attempt.
    The values are not recorded: nobody believes them, and an audit line must not
    become a channel for a caller's chosen text.
    """
    from_query = _present(request.query_params)
    if len(from_query) != len(GRANT_PARAM_NAMES):
        return

    emit_audit_log(
        AUDIT_GRANT_REJECTED,
        "warning",
        outcome="rejected",
        reason="caller_not_allow_listed",
    )


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
    "CallerPolicy",
    "DelegationConfig",
    "DelegationGrant",
    "get_delegation_config",
    "initialize_delegation",
    "require_workload_caller",
    "resolve_delegated_principal",
    "scrub_grant_text",
]
