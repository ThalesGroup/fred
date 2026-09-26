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
from collections.abc import Iterator

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
    DelegationConfig,
    DelegationGrant,
    bears_service_account_markers,
    get_delegation_config,
    holds_caller_role,
    initialize_delegation,
    is_delegation_caller,
    preserved_delegation,
    read_caller_roles,
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
_ISSUER = "https://identity.invalid/realms/test"
_LOGIN_CLIENT = "app"
_OTHER_ISSUER = "https://other.invalid/realms/test"
_ACCESS_KIND = "Bearer"
_ID_KIND = "ID"
_REFRESH_KIND = "Refresh"
_THIRD_ISSUER = "https://third.invalid/realms/test"


def _security_block(delegation: dict) -> dict:
    return {
        "m2m": {"realm_url": "http://idp/realms/app", "client_id": "app"},
        "user": {"realm_url": "http://idp/realms/app", "client_id": "app"},
        "delegation": delegation,
    }


@pytest.fixture(autouse=True)
def _restore_delegation() -> Iterator[None]:
    with preserved_delegation():
        yield


def _install(config: DelegationConfig | None = None) -> None:
    initialize_delegation(
        config or DelegationConfig(accept_delegated_calls=True),
        issuers=[_ISSUER],
        user_clients=[_LOGIN_CLIENT],
    )


def _grant_request() -> Request:
    """A whole, valid grant offered in the query."""
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/read",
            "query_string": b"person=p-1&run=r-1&agent=a-1",
            "headers": [],
        }
    )


def _workload(**update: object) -> KeycloakUser:
    """A verified workload token carrying everything a receiver requires."""
    return KeycloakUser(
        uid="any-service-account",
        username="service",
        roles=[],
        client_id=_CALLER,
        token_issuer=_ISSUER,
        token_audiences=frozenset({"fred-delegation"}),
        token_type=_ACCESS_KIND,
        caller_roles=frozenset({"delegation_caller"}),
    ).model_copy(update=update)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_delegation_is_off_by_default_with_the_role_convention() -> None:
    config = DelegationConfig()

    assert config.act_for_people is False
    assert config.accept_delegated_calls is False
    assert config.in_use is False
    assert config.audience == "fred-delegation"
    assert config.caller_role == "delegation_caller"
    assert config.caller_roles_claim is None
    assert config.roles_claim_path == ("resource_access", "fred-delegation", "roles")
    assert config.user_clients == []
    assert config.service_accounts_only is False


def test_the_default_roles_claim_follows_the_audience() -> None:
    _install(
        DelegationConfig(accept_delegated_calls=True, audience="another-delegation")
    )
    payload = {
        "resource_access": {"another-delegation": {"roles": ["delegation_caller"]}}
    }

    assert read_caller_roles(payload) == frozenset({"delegation_caller"})


def test_either_switch_needs_no_per_caller_configuration() -> None:
    assert DelegationConfig(act_for_people=True).in_use is True
    assert DelegationConfig(accept_delegated_calls=True).in_use is True


@pytest.mark.parametrize("value", [True, False])
def test_the_single_switch_is_refused_naming_both_directions(value: bool) -> None:
    # The refusal must name both replacements, not just reject an unknown key.
    with pytest.raises(ValidationError, match="act_for_people.*accept_delegated_calls"):
        DelegationConfig.model_validate({"enabled": value})


@pytest.mark.parametrize("retired", ["allowed_callers", "caller_policies"])
def test_a_retired_caller_list_is_refused(retired: str) -> None:
    with pytest.raises(ValidationError) as exc:
        DelegationConfig.model_validate({"accept_delegated_calls": True, retired: []})

    assert retired in str(exc.value)


def test_an_unknown_delegation_field_is_refused() -> None:
    with pytest.raises(ValidationError, match="unknown_field"):
        DelegationConfig.model_validate(
            {"accept_delegated_calls": True, "unknown_field": "x"}
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("audience", "   "),
        ("caller_role", "   "),
        ("caller_roles_claim", []),
        ("caller_roles_claim", ["roles", " "]),
        ("user_clients", ["  "]),
    ],
)
def test_a_blank_setting_is_refused(field: str, value: object) -> None:
    with pytest.raises(ValidationError, match=field):
        DelegationConfig.model_validate({"accept_delegated_calls": True, field: value})


# ---------------------------------------------------------------------------
# Caller trust
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_grant_from_a_role_holder_is_accepted() -> None:
    _install()

    asserted = await resolve_delegated_principal(_grant_request(), _workload())

    assert asserted is not None
    assert asserted.uid == "p-1"
    assert asserted.client_id == _CALLER
    assert asserted.run_id == "r-1"
    assert asserted.agent_id == "a-1"


@pytest.mark.parametrize(
    "identity",
    [
        {"uid": "one-service-account", "client_id": "one-client"},
        {"uid": "another-service-account", "client_id": "another-client"},
    ],
)
def test_any_role_holder_is_trusted_whatever_its_client_and_subject(
    identity: dict[str, object],
) -> None:
    # No receiver names its callers: the role is the whole of caller trust.
    _install()

    require_workload_caller(_workload(**identity))

    assert is_delegation_caller(_workload(**identity)) is True


@pytest.mark.parametrize(
    "update",
    [
        {"caller_roles": frozenset()},
        {"caller_roles": frozenset({"another_role"})},
        {"token_type": _ID_KIND},
        {"token_issuer": _OTHER_ISSUER},
        {"token_audiences": frozenset({"another-receiver"})},
        {"client_id": _LOGIN_CLIENT},
        {"client_id": None},
        {"token_type": _REFRESH_KIND},
    ],
)
def test_a_single_mismatch_refuses_the_caller(update: dict[str, object]) -> None:
    _install()

    with pytest.raises(HTTPException) as raised:
        require_workload_caller(_workload(**update))

    assert raised.value.status_code == 403
    assert raised.value.detail == "workload_caller_not_allowed"


@pytest.mark.parametrize("token_type", [None, "at+jwt"])
def test_an_access_token_labelled_otherwise_or_not_at_all_can_delegate(
    token_type: str | None,
) -> None:
    _install()

    assert is_delegation_caller(_workload(token_type=token_type)) is True


def test_a_client_people_sign_in_through_is_refused_even_when_listed_only_in_the_block() -> (
    None
):
    _install(DelegationConfig(accept_delegated_calls=True, user_clients=["portal"]))

    assert is_delegation_caller(_workload(client_id="portal")) is False
    assert is_delegation_caller(_workload(client_id=_LOGIN_CLIENT)) is False
    assert is_delegation_caller(_workload()) is True


def test_either_realm_address_is_trusted() -> None:
    initialize_delegation(
        DelegationConfig(accept_delegated_calls=True),
        issuers=[_ISSUER, _OTHER_ISSUER + "/"],
        user_clients=[_LOGIN_CLIENT],
    )

    assert is_delegation_caller(_workload()) is True
    assert is_delegation_caller(_workload(token_issuer=_OTHER_ISSUER)) is True
    assert is_delegation_caller(_workload(token_issuer=_ISSUER + "/")) is True
    assert is_delegation_caller(_workload(token_issuer=_THIRD_ISSUER)) is False


def test_preserved_delegation_restores_what_was_installed() -> None:
    _install()

    with preserved_delegation():
        initialize_delegation(DelegationConfig(), issuers=[_OTHER_ISSUER])
        assert is_delegation_caller(_workload()) is False

    assert get_delegation_config().accept_delegated_calls is True
    assert is_delegation_caller(_workload()) is True


@pytest.mark.parametrize(
    ("claims", "expected"),
    [
        (
            {"preferred_username": "service-account-agentic", "client_id": "agentic"},
            True,
        ),
        (
            {"preferred_username": "service-account-agentic", "clientId": "agentic"},
            True,
        ),
        (
            {"preferred_username": "Service-Account-Agentic", "client_id": "agentic"},
            True,
        ),
        ({"preferred_username": "alice", "client_id": "agentic"}, False),
        ({"preferred_username": "service-account-agentic"}, False),
        (
            {"preferred_username": "service-account-other", "client_id": "agentic"},
            False,
        ),
        (
            {"preferred_username": "service-account-agentic", "client_id": "other"},
            False,
        ),
        ({"client_id": "agentic"}, False),
    ],
)
def test_keycloak_service_account_markers(
    claims: dict[str, str], expected: bool
) -> None:
    assert bears_service_account_markers(claims, "agentic") is expected


def test_with_service_accounts_only_a_token_without_the_markers_never_delegates() -> (
    None
):
    _install(DelegationConfig(accept_delegated_calls=True, service_accounts_only=True))

    assert is_delegation_caller(_workload(service_account=True)) is True
    # A person's token from a client nobody listed carries the role but no markers.
    assert is_delegation_caller(_workload(client_id="unlisted-portal")) is False


def test_without_the_option_the_markers_are_not_required() -> None:
    _install()

    assert is_delegation_caller(_workload(service_account=False)) is True


def test_while_delegation_is_off_the_role_is_recognised_but_nothing_is_trusted() -> (
    None
):
    # A delegation client holds the service role too; recognising it keeps it off
    # the service-identity shortcuts even where no grant is believed.
    _install(DelegationConfig())
    service_identity = _workload(roles=[SERVICE_AGENT_ROLE], caller_roles=frozenset())

    assert holds_caller_role(_workload()) is True
    assert holds_caller_role(service_identity) is False
    assert is_delegation_caller(_workload()) is False
    with pytest.raises(HTTPException):
        require_workload_caller(_workload())


@pytest.mark.asyncio
async def test_acting_for_people_alone_reads_the_role_but_believes_no_grant() -> None:
    # Calling others for a person must not make this backend believe the person
    # a role holder names to it; only accepting delegated calls does.
    _install(DelegationConfig(act_for_people=True))

    assert holds_caller_role(_workload()) is True
    assert is_delegation_caller(_workload()) is False
    assert await resolve_delegated_principal(_grant_request(), _workload()) is None
    with pytest.raises(HTTPException):
        require_workload_caller(_workload())


def test_the_role_is_read_from_the_configured_claim_only() -> None:
    _install()
    payload = {
        "resource_access": {
            "fred-delegation": {"roles": ["delegation_caller", 7, ""]},
            "app": {"roles": ["service_agent"]},
        }
    }

    assert read_caller_roles(payload) == frozenset({"delegation_caller"})
    assert (
        read_caller_roles(
            {"resource_access": {"app": {"roles": ["delegation_caller"]}}}
        )
        == frozenset()
    )
    assert (
        read_caller_roles(
            {"resource_access": {"fred-delegation": {"roles": "delegation_caller"}}}
        )
        == frozenset()
    )


def test_another_provider_names_its_own_roles_claim() -> None:
    _install(
        DelegationConfig(
            accept_delegated_calls=True,
            caller_roles_claim=["roles"],
            caller_role="Fred.Delegate",
        )
    )

    assert read_caller_roles({"roles": ["Fred.Delegate"]}) == frozenset(
        {"Fred.Delegate"}
    )
    # Such a provider labels no token type; the role and the rest still decide.
    assert is_delegation_caller(
        _workload(token_type=None, caller_roles=frozenset({"Fred.Delegate"}))
    )


def test_a_claim_name_containing_dots_is_one_path_entry() -> None:
    _install(
        DelegationConfig(
            accept_delegated_calls=True,
            caller_roles_claim=["https://fred.invalid/roles"],
        )
    )

    assert read_caller_roles(
        {"https://fred.invalid/roles": ["delegation_caller"]}
    ) == frozenset({"delegation_caller"})


def test_the_roles_are_read_while_delegation_is_off() -> None:
    _install(DelegationConfig())

    assert read_caller_roles(
        {"resource_access": {"fred-delegation": {"roles": ["delegation_caller"]}}}
    ) == frozenset({"delegation_caller"})


def test_an_asserted_person_never_holds_the_caller_role() -> None:
    _install()

    assert holds_caller_role(_asserted()) is False
    assert holds_caller_role(_workload()) is True


@pytest.mark.parametrize("switch", ["act_for_people", "accept_delegated_calls"])
def test_security_configuration_accepts_one_switch_on_its_own(switch: str) -> None:
    security = SecurityConfiguration.model_validate(_security_block({switch: True}))

    assert getattr(security.delegation, switch) is True
    assert security.delegation.caller_role == "delegation_caller"


def test_security_configuration_refuses_the_single_switch() -> None:
    with pytest.raises(ValidationError, match="act_for_people.*accept_delegated_calls"):
        SecurityConfiguration.model_validate(_security_block({"enabled": True}))


def test_security_configuration_refuses_a_retired_caller_list() -> None:
    # The whole security block is what a backend parses at startup, so the
    # refusal must reach the configuration banner, not only the nested model.
    with pytest.raises(ValidationError, match="caller_policies"):
        SecurityConfiguration.model_validate(
            _security_block({"accept_delegated_calls": True, "caller_policies": []})
        )


def test_security_configuration_defaults_to_delegation_off() -> None:
    security = SecurityConfiguration.model_validate(
        {
            "m2m": {"realm_url": "http://idp/realms/app", "client_id": "app"},
            "user": {"realm_url": "http://idp/realms/app", "client_id": "app"},
        }
    )

    assert security.delegation.in_use is False


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
        "holds_caller_role": holds_caller_role,
        "initialize_delegation": initialize_delegation,
        "is_delegation_caller": is_delegation_caller,
        "require_own_credential": require_own_credential,
        "require_workload_caller": require_workload_caller,
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
