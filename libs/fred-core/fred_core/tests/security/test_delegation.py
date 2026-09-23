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

"""Delegation configuration, grant shape and the asserted principal.

Acceptance through the shared user dependency lives in test_oidc_delegation.py.
"""

from __future__ import annotations

import dataclasses

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

import fred_core
from fred_core.security.delegation import (
    GRANT_PARAM_AGENT,
    GRANT_PARAM_NAMES,
    GRANT_PARAM_PERSON,
    GRANT_PARAM_RUN,
    AssertedUser,
    CallerPolicy,
    DelegationConfig,
    DelegationGrant,
    get_delegation_config,
    initialize_delegation,
    require_workload_caller,
    resolve_delegated_principal,
    scrub_grant_text,
)
from fred_core.security.oidc import require_own_credential
from fred_core.security.structure import (
    SERVICE_AGENT_ROLE,
    KeycloakUser,
    Principal,
    SecurityConfiguration,
    is_service_agent,
)

_CALLER = "agent-backend"


def _security_block(delegation: dict) -> dict:
    return {
        "m2m": {"realm_url": "http://idp/realms/app", "client_id": "app"},
        "user": {"realm_url": "http://idp/realms/app", "client_id": "app"},
        "delegation": delegation,
    }


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_delegation_is_off_and_empty_by_default() -> None:
    config = DelegationConfig()

    assert config.enabled is False
    assert config.allowed_callers == []


def test_enabled_without_an_allow_list_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        DelegationConfig(enabled=True)

    assert "allowed_callers" in str(exc.value)


def test_enabled_with_only_blank_callers_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DelegationConfig(enabled=True, allowed_callers=["", "   "])


def test_enabled_with_one_caller_is_accepted() -> None:
    config = DelegationConfig(enabled=True, allowed_callers=[_CALLER])

    assert config.enabled is True
    assert config.allowed_callers == [_CALLER]


def test_string_only_caller_never_authorizes_a_delegated_subject() -> None:
    config = DelegationConfig(enabled=True, allowed_callers=[_CALLER])

    assert config.policy_for(client_id=_CALLER, subject="service-sub") is None


def test_exact_caller_and_subject_select_the_policy() -> None:
    policy = CallerPolicy(
        client_id=_CALLER,
        subject="service-sub",
    )
    config = DelegationConfig(enabled=True, caller_policies=[policy])

    assert config.policy_for(client_id=_CALLER, subject="service-sub") is policy
    assert config.policy_for(client_id=_CALLER, subject="human-sub") is None


def test_caller_policy_rejects_unknown_configuration_fields() -> None:
    with pytest.raises(ValidationError, match="unknown_field"):
        CallerPolicy.model_validate(
            {
                "client_id": _CALLER,
                "subject": "service-sub",
                "unknown_field": "unexpected",
            }
        )


@pytest.mark.asyncio
async def test_valid_grant_from_a_trusted_identity_is_accepted() -> None:
    initialize_delegation(
        DelegationConfig(
            enabled=True,
            caller_policies=[
                CallerPolicy(
                    client_id=_CALLER,
                    subject="service-sub",
                )
            ],
        ),
        issuer="https://identity.invalid/realms/test",
        audience="receiver",
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/read",
            "query_string": b"person=p-1&run=r-1&agent=a-1",
            "headers": [],
        }
    )
    caller = KeycloakUser(
        uid="service-sub",
        username="service",
        roles=[SERVICE_AGENT_ROLE],
        client_id=_CALLER,
        token_issuer="https://identity.invalid/realms/test",  # nosec B106 - protocol metadata or synthetic fixture
        token_audiences=frozenset({"receiver"}),
        token_type="Bearer",
    )

    asserted = await resolve_delegated_principal(request, caller)

    assert asserted is not None
    assert asserted.uid == "p-1"
    assert asserted.run_id == "r-1"
    assert asserted.agent_id == "a-1"


def test_caller_only_policy_accepts_the_exact_verified_workload() -> None:
    initialize_delegation(
        DelegationConfig(
            enabled=True,
            caller_policies=[
                CallerPolicy(
                    client_id=_CALLER,
                    subject="service-sub",
                )
            ],
        ),
        issuer="https://identity.invalid/realms/test",
        audience="receiver",
    )
    caller = KeycloakUser(
        uid="service-sub",
        username="service",
        roles=[SERVICE_AGENT_ROLE],
        client_id=_CALLER,
        token_issuer="https://identity.invalid/realms/test",  # nosec B106 - protocol metadata or synthetic fixture
        token_audiences=frozenset({"receiver"}),
        token_type="Bearer",
    )

    policy = require_workload_caller(caller)

    assert policy.client_id == _CALLER
    assert policy.subject == "service-sub"


@pytest.mark.parametrize(
    "update",
    [
        {"uid": "other-subject"},
        {"client_id": "other-client"},
        {"token_type": "ID"},  # nosec B105 - protocol metadata or synthetic fixture
        {"token_issuer": "https://other.invalid/realms/test"},  # nosec B105 - protocol metadata or synthetic fixture
        {"token_audiences": frozenset({"other-receiver"})},
    ],
)
def test_caller_only_policy_rejects_any_identity_or_token_mismatch(
    update: dict[str, object],
) -> None:
    initialize_delegation(
        DelegationConfig(
            enabled=True,
            caller_policies=[
                CallerPolicy(
                    client_id=_CALLER,
                    subject="service-sub",
                )
            ],
        ),
        issuer="https://identity.invalid/realms/test",
        audience="receiver",
    )
    caller = KeycloakUser(
        uid="service-sub",
        username="service",
        roles=[SERVICE_AGENT_ROLE],
        client_id=_CALLER,
        token_issuer="https://identity.invalid/realms/test",  # nosec B106 - protocol metadata or synthetic fixture
        token_audiences=frozenset({"receiver"}),
        token_type="Bearer",
    ).model_copy(update=update)

    with pytest.raises(HTTPException) as raised:
        require_workload_caller(caller)

    assert raised.value.status_code == 403
    assert raised.value.detail == "workload_caller_not_allowed"


def test_security_configuration_rejects_an_enabled_block_without_callers() -> None:
    # The whole security block is what a backend parses at startup, so the
    # refusal must reach the configuration banner, not only the nested model.
    with pytest.raises(ValidationError):
        SecurityConfiguration.model_validate(
            _security_block({"enabled": True, "allowed_callers": []})
        )


def test_security_configuration_accepts_a_configured_block() -> None:
    security = SecurityConfiguration.model_validate(
        _security_block({"enabled": True, "allowed_callers": [_CALLER]})
    )

    assert security.delegation.allows(_CALLER) is True


def test_security_configuration_defaults_to_delegation_off() -> None:
    security = SecurityConfiguration.model_validate(
        {
            "m2m": {"realm_url": "http://idp/realms/app", "client_id": "app"},
            "user": {"realm_url": "http://idp/realms/app", "client_id": "app"},
        }
    )

    assert security.delegation.enabled is False


def test_allows_only_a_listed_caller() -> None:
    config = DelegationConfig(enabled=True, allowed_callers=[_CALLER])

    assert config.allows(_CALLER) is True
    assert config.allows("another-client") is False
    assert config.allows(None) is False
    assert config.allows("") is False


def test_a_blank_allow_list_entry_never_matches() -> None:
    config = DelegationConfig(enabled=True, allowed_callers=[_CALLER, "   "])

    assert config.allows("   ") is False
    assert config.allows("") is False


# ---------------------------------------------------------------------------
# Grant shape
# ---------------------------------------------------------------------------


def test_grant_accepts_three_identifiers_and_trims_them() -> None:
    grant = DelegationGrant(person=" p-1 ", run="r-1", agent="a-1")

    assert (grant.person, grant.run, grant.agent) == ("p-1", "r-1", "a-1")


@pytest.mark.parametrize(
    "payload",
    [
        {"person": "p-1", "run": "r-1"},
        {"person": "", "run": "r-1", "agent": "a-1"},
        {"person": "   ", "run": "r-1", "agent": "a-1"},
        {"person": 7, "run": "r-1", "agent": "a-1"},
        {"person": {"uid": "p-1"}, "run": "r-1", "agent": "a-1"},
        {"person": "p" * 257, "run": "r-1", "agent": "a-1"},
    ],
)
def test_grant_refuses_an_incomplete_or_malformed_set(payload: dict) -> None:
    with pytest.raises(ValidationError):
        DelegationGrant.model_validate(payload)


# ---------------------------------------------------------------------------
# Asserted principal
# ---------------------------------------------------------------------------


def _asserted() -> AssertedUser:
    return AssertedUser(uid="p-1", client_id=_CALLER, run_id="r-1", agent_id="a-1")


def test_asserted_principal_carries_the_person_the_caller_the_run_and_the_agent() -> (
    None
):
    asserted = _asserted()

    assert asserted.uid == "p-1"
    assert asserted.client_id == _CALLER
    assert asserted.run_id == "r-1"
    assert asserted.agent_id == "a-1"


def test_asserted_principal_is_not_a_keycloak_user() -> None:
    assert not isinstance(_asserted(), KeycloakUser)


def test_asserted_principal_never_holds_the_service_role() -> None:
    assert _asserted().roles == []
    assert is_service_agent(_asserted()) is False
    # The role is a real one: the predicate is False because the principal has
    # no roles, not because the predicate never fires.
    assert (
        is_service_agent(
            KeycloakUser(uid="svc", username="svc", roles=[SERVICE_AGENT_ROLE])
        )
        is True
    )


def test_asserted_principal_cannot_be_given_roles() -> None:
    with pytest.raises(TypeError):
        AssertedUser(
            uid="p-1",
            client_id=_CALLER,
            run_id="r-1",
            agent_id="a-1",
            roles=[SERVICE_AGENT_ROLE],  # type: ignore
        )


def test_asserted_principal_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _asserted().uid = "someone-else"  # type: ignore[misc]


def test_the_delegation_surface_is_reachable_from_the_package_root() -> None:
    # Receivers import from `fred_core`, not from the private module paths, and
    # CodeQL only counts a re-export that is named in `__all__`.
    exported = {
        "AssertedUser": AssertedUser,
        "DelegationConfig": DelegationConfig,
        "DelegationGrant": DelegationGrant,
        "GRANT_PARAM_AGENT": GRANT_PARAM_AGENT,
        "GRANT_PARAM_NAMES": GRANT_PARAM_NAMES,
        "GRANT_PARAM_PERSON": GRANT_PARAM_PERSON,
        "GRANT_PARAM_RUN": GRANT_PARAM_RUN,
        "Principal": Principal,
        "get_delegation_config": get_delegation_config,
        "initialize_delegation": initialize_delegation,
        "require_own_credential": require_own_credential,
        "resolve_delegated_principal": resolve_delegated_principal,
    }

    for name, obj in exported.items():
        assert getattr(fred_core, name) is obj, name
        assert name in fred_core.__all__, name


def test_both_kinds_satisfy_the_permission_check_shape() -> None:
    assert isinstance(_asserted(), Principal)
    assert isinstance(
        KeycloakUser(uid="u-1", username="u", roles=["admin"], client_id="frontend"),
        Principal,
    )


# ---------------------------------------------------------------------------
# Grant values never reach a log line through a quoted URL
# ---------------------------------------------------------------------------


def test_scrub_grant_text_drops_the_values_from_a_url_inside_text() -> None:
    text = (
        "Client error '401 Unauthorized' for url "
        "'http://receiver.invalid/mcp?x=1&person=uid-1&run=run-1&agent=agent-1'"
    )

    scrubbed = scrub_grant_text(text)

    for value in ("uid-1", "run-1", "agent-1"):
        assert value not in scrubbed
    assert "x=1" in scrubbed
    assert "person=&run=&agent=" in scrubbed
    assert scrubbed.startswith("Client error '401 Unauthorized' for url")


def test_scrub_grant_text_leaves_other_text_alone() -> None:
    text = "GET http://receiver.invalid/documents?personal=1&runner=2 failed"

    assert scrub_grant_text(text) == text
    assert fred_core.scrub_grant_text is scrub_grant_text
