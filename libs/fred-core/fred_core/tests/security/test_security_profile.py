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

"""Tests for the C3 security profile (RUNTIME-07 rev. 2, F5/F6).

The C3 profile forces strict JWT issuer/audience validation, forbids
no-security/mock-admin, and requires OpenFGA ReBAC to be enabled so the pod
authorizes every request and fails closed. There is no signed grant.
"""

from typing import Literal

import pytest
from pydantic import AnyHttpUrl, AnyUrl, ValidationError

from fred_core.security import delegation, oidc
from fred_core.security.delegation import DelegationConfig, is_delegation_caller
from fred_core.security.structure import (
    KeycloakUser,
    M2MSecurity,
    OpenFgaRebacConfig,
    SecurityConfiguration,
    UserSecurity,
)

_REALM = AnyUrl("http://localhost:8080/realms/app")
_ACCESS_KIND = "Bearer"


def _security(
    *,
    profile: Literal["c3"] | None = None,
    user: bool = True,
    m2m: bool = True,
    rebac: bool = True,
    accept_delegated_calls: bool = False,
    m2m_realm: AnyUrl = _REALM,
    user_client: str = "app",
    user_clients: tuple[str, ...] = (),
):
    rebac_cfg = (
        OpenFgaRebacConfig(enabled=rebac, api_url=AnyHttpUrl("http://fga:8080"))
        if rebac
        else None
    )
    return SecurityConfiguration(
        m2m=M2MSecurity(enabled=m2m, realm_url=m2m_realm, client_id="cp"),
        user=UserSecurity(enabled=user, realm_url=_REALM, client_id=user_client),
        rebac=rebac_cfg,
        profile=profile,
        delegation=DelegationConfig(
            accept_delegated_calls=accept_delegated_calls,
            user_clients=list(user_clients),
        ),
    )


@pytest.fixture(autouse=True)
def _restore_security_profile_globals():
    before = (oidc.STRICT_ISSUER, oidc.STRICT_AUDIENCE, oidc._REALM_ISSUERS)
    with delegation.preserved_delegation():
        yield
    oidc.STRICT_ISSUER, oidc.STRICT_AUDIENCE, oidc._REALM_ISSUERS = before


def test_non_c3_profile_is_noop() -> None:
    oidc.STRICT_ISSUER = False
    oidc.STRICT_AUDIENCE = False
    oidc.apply_security_profile(_security(profile=None, user=False, rebac=False))
    # No exception, and strict flags untouched.
    assert oidc.STRICT_ISSUER is False
    assert oidc.STRICT_AUDIENCE is False


def test_c3_profile_forces_strict_jwt() -> None:
    oidc.STRICT_ISSUER = False
    oidc.STRICT_AUDIENCE = False
    oidc.apply_security_profile(_security(profile="c3"))
    assert oidc.STRICT_ISSUER is True
    assert oidc.STRICT_AUDIENCE is True


def test_c3_rejects_no_security() -> None:
    with pytest.raises(ValueError, match="user.enabled must be true"):
        oidc.apply_security_profile(_security(profile="c3", user=False))


def test_c3_requires_m2m() -> None:
    with pytest.raises(ValueError, match="m2m.enabled must be true"):
        oidc.apply_security_profile(_security(profile="c3", m2m=False))


def test_c3_requires_rebac_enabled() -> None:
    with pytest.raises(ValueError, match="rebac.enabled must be true"):
        oidc.apply_security_profile(_security(profile="c3", rebac=False))


def test_c3_happy_path_does_not_raise() -> None:
    oidc.apply_security_profile(_security(profile="c3"))  # no exception


def test_the_former_setting_name_is_refused_rather_than_ignored() -> None:
    """Ignored, a stale key would leave the check off without a word."""
    with pytest.raises(ValidationError, match="standing_gate_enabled was removed"):
        OpenFgaRebacConfig.model_validate(
            {"api_url": "http://authz.invalid:9080", "standing_gate_enabled": True}
        )


def _bearer(client_id: str, issuer: str = str(_REALM)) -> KeycloakUser:
    return KeycloakUser(
        uid="any-account",
        username="any-account",
        roles=[],
        client_id=client_id,
        token_issuer=issuer.rstrip("/"),
        token_audiences=frozenset({"fred-delegation"}),
        token_type=_ACCESS_KIND,
        caller_roles=frozenset({"delegation_caller"}),
    )


def test_startup_trusts_role_holders_of_this_realm_other_than_the_login_client() -> (
    None
):
    oidc.apply_security_profile(_security(accept_delegated_calls=True))

    assert is_delegation_caller(_bearer("a-workload"))
    assert not is_delegation_caller(_bearer("app"))
    assert not is_delegation_caller(
        _bearer("a-workload", issuer="http://localhost:8080/realms/other")
    )


def test_startup_trusts_the_realm_under_its_workload_address_too() -> None:
    internal = "http://keycloak.internal:8080/realms/app"
    oidc.apply_security_profile(
        _security(accept_delegated_calls=True, m2m_realm=AnyUrl(internal))
    )

    assert is_delegation_caller(_bearer("a-workload", issuer=internal))
    assert is_delegation_caller(_bearer("a-workload"))
    assert oidc._REALM_ISSUERS == {str(_REALM).rstrip("/"), internal}


def test_a_receiver_with_its_own_audience_client_refuses_the_listed_login_client() -> (
    None
):
    oidc.apply_security_profile(
        _security(
            accept_delegated_calls=True,
            user_client="an-agent-pod",
            user_clients=("app",),
        )
    )

    assert not is_delegation_caller(_bearer("app"))
    assert not is_delegation_caller(_bearer("an-agent-pod"))
    assert is_delegation_caller(_bearer("a-workload"))


def test_the_retired_workload_audience_setting_is_refused() -> None:
    with pytest.raises(ValidationError, match="audience"):
        M2MSecurity.model_validate(
            {"realm_url": str(_REALM), "client_id": "cp", "audience": "an-old-one"}
        )
