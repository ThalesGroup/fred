"""The security profile a first-party application receives from its environment.

Every installed application ran its own copy of this assembly, so a rule was
only as good as the copy that happened to be read. These cases pin the rules
themselves.
"""

from __future__ import annotations

import json

import pytest

from fred_core.security.env_config import security_configuration_from_env

SHARED = {
    "KEYCLOAK_REALM_URL": "http://identity.invalid/realms/app",
    "KEYCLOAK_USER_AUDIENCE": "a-browser-client",
    "KEYCLOAK_M2M_CLIENT_ID": "an-app-workload",
    "OPENFGA_API_URL": "http://authz.invalid:9080",
}
OWN = {
    "m2m_secret_env": "AN_APP_M2M_CLIENT_SECRET",  # nosec B105 - variable name  # pragma: allowlist secret
    "openfga_token_env": "AN_APP_OPENFGA_API_TOKEN",  # nosec B105 - variable name
}
OPTIONAL = (
    "KEYCLOAK_M2M_REALM_URL",
    "KEYCLOAK_M2M_AUDIENCE",
    "OPENFGA_STORE_NAME",
    "OPENFGA_AUTHORIZATION_MODEL_ID",
    "FRED_DELEGATION",
)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name, value in SHARED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv(
        OWN["m2m_secret_env"], "not-a-real-secret"
    )  # pragma: allowlist secret
    monkeypatch.setenv(
        OWN["openfga_token_env"], "not-a-real-token"
    )  # pragma: allowlist secret
    for name in OPTIONAL:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_two_applications_differ_only_by_the_names_that_are_their_own(
    env: pytest.MonkeyPatch,
) -> None:
    """The shared rules are not restated per application, so they cannot drift."""
    env.setenv(
        "ANOTHER_APP_M2M_CLIENT_SECRET", "not-a-real-secret"
    )  # pragma: allowlist secret
    env.setenv(
        "ANOTHER_APP_OPENFGA_API_TOKEN", "not-a-real-token"
    )  # pragma: allowlist secret

    one = security_configuration_from_env(**OWN)
    another = security_configuration_from_env(
        m2m_secret_env="ANOTHER_APP_M2M_CLIENT_SECRET",  # nosec B106 - variable name  # pragma: allowlist secret
        openfga_token_env="ANOTHER_APP_OPENFGA_API_TOKEN",  # nosec B106 - variable name
    )

    assert one.profile == another.profile == "c3"
    assert one.rebac is not None and another.rebac is not None
    assert one.rebac.enabled and another.rebac.enabled
    # A first-party application reads the shared model; it never owns it.
    assert not one.rebac.create_store_if_needed
    assert not one.rebac.sync_schema_on_init
    assert one.m2m.secret_env_var != another.m2m.secret_env_var


def test_one_realm_serves_both_principals_until_the_issuers_differ(
    env: pytest.MonkeyPatch,
) -> None:
    config = security_configuration_from_env(**OWN)
    assert str(config.m2m.realm_url) == str(config.user.realm_url)


def test_a_workload_token_may_be_minted_where_a_browser_token_never_is(
    env: pytest.MonkeyPatch,
) -> None:
    """A browser token carries the address the person signed in at; a workload
    token the address it was minted at. One value cannot validate both."""
    env.setenv("KEYCLOAK_M2M_REALM_URL", "http://in-cluster.invalid/realms/app")

    config = security_configuration_from_env(**OWN)

    assert "in-cluster.invalid" in str(config.m2m.realm_url)
    assert "identity.invalid" in str(config.user.realm_url)


def test_delegation_is_off_until_the_deployment_asks_for_it(
    env: pytest.MonkeyPatch,
) -> None:
    config = security_configuration_from_env(**OWN)
    assert config.delegation.enabled is False
    assert config.delegation.caller_policies == []


def test_an_enabled_grant_names_the_workloads_allowed_to_speak_for_people(
    env: pytest.MonkeyPatch,
) -> None:
    env.setenv(
        "FRED_DELEGATION",
        json.dumps(
            {
                "enabled": True,
                "caller_policies": [{"client_id": "a-runtime", "subject": "a-subject"}],
            }
        ),
    )

    delegation = security_configuration_from_env(**OWN).delegation

    assert delegation.enabled is True
    assert delegation.allows("a-runtime")
    assert not delegation.allows("someone-else")


@pytest.mark.parametrize("raw", ["not json", '["a list"]', '"a string"'])
def test_an_unreadable_grant_stops_startup_instead_of_disabling_delegation(
    env: pytest.MonkeyPatch, raw: str
) -> None:
    """Falling back to "off" would turn a typo into an outage whose cause shows
    up only much later, as calls refused for no stated reason."""
    env.setenv("FRED_DELEGATION", raw)
    with pytest.raises(RuntimeError):
        security_configuration_from_env(**OWN)


def test_an_enabled_grant_trusting_nobody_is_refused(env: pytest.MonkeyPatch) -> None:
    env.setenv("FRED_DELEGATION", json.dumps({"enabled": True}))
    with pytest.raises(ValueError):
        security_configuration_from_env(**OWN)


def test_the_receiver_audience_defaults_to_the_applications_own_workload(
    env: pytest.MonkeyPatch,
) -> None:
    """A receiver demands its own identity in a caller's token unless the
    deployment names a different audience."""
    assert security_configuration_from_env(**OWN).m2m.audience is None

    env.setenv("KEYCLOAK_M2M_AUDIENCE", "a-shared-audience")

    assert security_configuration_from_env(**OWN).m2m.audience == "a-shared-audience"
