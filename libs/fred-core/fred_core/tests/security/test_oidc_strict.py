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


"""Strict JWT validation under the C3 profile (RUNTIME-07 rev. 2, finding F-E).

When STRICT_ISSUER / STRICT_AUDIENCE are set, decode_jwt must enforce EXACT issuer
and audience on the signature-verified payload (PyJWT verify_aud=True), not a
prefix/peek check. These tests sign real RS256 tokens and mock only the JWKS key
resolution.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from fred_core.security import delegation, oidc
from fred_core.security.delegation import DelegationConfig

_REALM = "http://localhost:8080/realms/app"
_CLIENT = "app"


@pytest.fixture
def _rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return priv_pem, key.public_key()


@pytest.fixture(autouse=True)
def _strict_keycloak(monkeypatch, _rsa_keypair):
    _, public_key = _rsa_keypair
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "KEYCLOAK_URL", _REALM)
    monkeypatch.setattr(oidc, "KEYCLOAK_CLIENT_ID", _CLIENT)
    monkeypatch.setattr(oidc, "_REALM_ISSUERS", frozenset({_REALM}))
    monkeypatch.setattr(oidc, "STRICT_ISSUER", True)
    monkeypatch.setattr(oidc, "STRICT_AUDIENCE", True)
    monkeypatch.setattr(
        oidc,
        "_get_jwks_client",
        lambda: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public_key)
        ),
    )


def _token(
    priv_pem: bytes,
    *,
    iss: str,
    aud: str | list[str],
    sub: str = "u-1",
    azp: str = "caller",
    typ: str = "Bearer",
    **claims: object,
) -> str:
    return pyjwt.encode(
        {
            "iss": iss,
            "aud": aud,
            "sub": sub,
            "preferred_username": "alice",
            "azp": azp,
            "typ": typ,
            "exp": int(time.time()) + 3600,
            **claims,
        },
        priv_pem,
        algorithm="RS256",
    )


def _installed(config: DelegationConfig) -> Iterator[None]:
    with delegation.preserved_delegation():
        delegation.initialize_delegation(
            config, issuers=[_REALM], user_clients=[_CLIENT]
        )
        yield


@pytest.fixture
def accepting_delegated_calls() -> Iterator[None]:
    yield from _installed(DelegationConfig(accept_delegated_calls=True))


@pytest.fixture(
    params=[DelegationConfig(), DelegationConfig(act_for_people=True)],
    ids=["delegation_off", "act_for_people_only"],
)
def not_accepting_delegated_calls(request: pytest.FixtureRequest) -> Iterator[None]:
    yield from _installed(request.param)


@pytest.fixture(
    params=[
        DelegationConfig(),
        DelegationConfig(act_for_people=True),
        DelegationConfig(accept_delegated_calls=True),
    ],
    ids=["delegation_off", "act_for_people", "accept_delegated_calls"],
)
def any_delegation_switches(request: pytest.FixtureRequest) -> Iterator[None]:
    yield from _installed(request.param)


_CALLER_ROLE = {"fred-delegation": {"roles": ["delegation_caller"]}}


def test_strict_accepts_exact_issuer_and_audience(_rsa_keypair):
    priv_pem, _ = _rsa_keypair
    user = oidc.decode_jwt(_token(priv_pem, iss=_REALM, aud=_CLIENT))
    assert user.uid == "u-1"
    assert user.client_id == "caller"
    assert user.token_issuer == _REALM
    assert user.token_audiences == frozenset({_CLIENT})
    assert user.token_type == "Bearer"  # nosec B105 - protocol metadata or synthetic fixture
    assert "token_issuer" not in user.model_dump()
    assert "token_audiences" not in user.model_dump()
    assert "token_type" not in user.model_dump()


def test_strict_rejects_wrong_audience(_rsa_keypair):
    priv_pem, _ = _rsa_keypair
    with pytest.raises(HTTPException) as exc:
        oidc.decode_jwt(_token(priv_pem, iss=_REALM, aud="some-other-client"))
    assert exc.value.status_code == 401


def test_strict_rejects_wrong_issuer(_rsa_keypair):
    priv_pem, _ = _rsa_keypair
    with pytest.raises(HTTPException) as exc:
        oidc.decode_jwt(
            _token(priv_pem, iss="http://evil/realms/app", aud=_CLIENT, sub="u-2")
        )
    assert exc.value.status_code == 401


def test_strict_rejects_issuer_prefix_attack(_rsa_keypair):
    """A prefix-matching issuer must be rejected under exact-match strict mode."""
    priv_pem, _ = _rsa_keypair
    with pytest.raises(HTTPException) as exc:
        oidc.decode_jwt(
            _token(priv_pem, iss=_REALM + ".evil.com", aud=_CLIENT, sub="u-3")
        )
    assert exc.value.status_code == 401


def test_strict_rejects_expired_token(_rsa_keypair):
    priv_pem, _ = _rsa_keypair
    token = pyjwt.encode(
        {
            "iss": _REALM,
            "aud": _CLIENT,
            "sub": "expired",
            "exp": int(time.time()) - 1,
        },
        priv_pem,
        algorithm="RS256",
    )

    with pytest.raises(HTTPException) as exc:
        oidc.decode_jwt(token)

    assert exc.value.status_code == 401


def test_strict_rejects_untrusted_signing_key(_rsa_keypair):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_private = other_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )

    with pytest.raises(HTTPException) as exc:
        oidc.decode_jwt(_token(other_private, iss=_REALM, aud=_CLIENT))

    assert exc.value.status_code == 401


def test_strict_rejects_an_unapproved_algorithm() -> None:
    token = pyjwt.encode(
        {
            "iss": _REALM,
            "aud": _CLIENT,
            "sub": "wrong-algorithm",
            "exp": int(time.time()) + 60,
        },
        "synthetic-signing-key-at-least-thirty-two-bytes",
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc:
        oidc.decode_jwt(token)

    assert exc.value.status_code == 401


def test_signed_id_token_retains_its_non_access_token_purpose(_rsa_keypair):
    priv_pem, _ = _rsa_keypair

    user = oidc.decode_jwt(_token(priv_pem, iss=_REALM, aud=_CLIENT, typ="ID"))

    assert user.token_type == "ID"  # nosec B105 - protocol metadata or synthetic fixture


def test_groups_claim_is_accepted_but_ignored(_rsa_keypair):
    """AUTHZ-05 final sweep: `KeycloakUser` no longer carries a `groups` field.

    A JWT still carrying a legacy `groups` claim (e.g. from an older Keycloak
    client scope) must decode successfully — the unknown claim is silently
    ignored, never raises, and never surfaces on the returned user.
    """
    priv_pem, _ = _rsa_keypair
    token = pyjwt.encode(
        {
            "iss": _REALM,
            "aud": _CLIENT,
            "sub": "u-4",
            "preferred_username": "alice",
            "exp": int(time.time()) + 3600,
            "groups": ["/thales", "/admins"],
        },
        priv_pem,
        algorithm="RS256",
    )

    user = oidc.decode_jwt(token)

    assert user.uid == "u-4"
    assert not hasattr(user, "groups")


def test_the_caller_role_is_read_from_the_signed_token(
    _rsa_keypair, any_delegation_switches
):
    # Read whatever the switches, so a delegation client is always recognised.
    priv_pem, _ = _rsa_keypair
    user = oidc.decode_jwt(
        _token(
            priv_pem,
            iss=_REALM,
            aud=_CLIENT,
            sub="svc-role",
            resource_access=_CALLER_ROLE,
        )
    )
    assert user.caller_roles == frozenset({"delegation_caller"})
    assert "caller_roles" not in user.model_dump()


def test_a_role_under_another_client_is_not_the_caller_role(
    _rsa_keypair, accepting_delegated_calls
):
    priv_pem, _ = _rsa_keypair
    user = oidc.decode_jwt(
        _token(
            priv_pem,
            iss=_REALM,
            aud=_CLIENT,
            sub="svc-other-client",
            resource_access={_CLIENT: {"roles": ["delegation_caller"]}},
        )
    )
    assert user.caller_roles == frozenset()


def test_strict_accepts_the_delegation_audience_for_a_delegating_workload(
    _rsa_keypair, accepting_delegated_calls
):
    """A receiver's login audience is not required of a workload speaking for a person."""
    priv_pem, _ = _rsa_keypair
    user = oidc.decode_jwt(
        _token(
            priv_pem,
            iss=_REALM,
            aud=["fred-delegation", "account"],
            sub="svc-delegating",
            azp="agentic",
            resource_access=_CALLER_ROLE,
        )
    )
    assert user.client_id == "agentic"
    assert user.caller_roles == frozenset({"delegation_caller"})


@pytest.mark.parametrize(
    ("azp", "resource_access"),
    [("agentic", {}), (_CLIENT, _CALLER_ROLE)],
    ids=["without-the-role", "login-client"],
)
def test_strict_refuses_the_delegation_audience_to_anyone_else(
    _rsa_keypair, accepting_delegated_calls, azp, resource_access
):
    priv_pem, _ = _rsa_keypair
    token = _token(
        priv_pem,
        iss=_REALM,
        aud="fred-delegation",
        azp=azp,
        resource_access=resource_access,
    )
    with pytest.raises(HTTPException) as exc:
        oidc.decode_jwt(token)
    assert exc.value.status_code == 401


def _addressed_to_the_delegation_audience_only(priv_pem: bytes) -> str:
    return _token(
        priv_pem,
        iss=_REALM,
        aud="fred-delegation",
        sub="svc-direction",
        azp="agentic",
        resource_access=_CALLER_ROLE,
    )


def test_strict_refuses_the_delegation_audience_unless_accepting_delegated_calls(
    _rsa_keypair, not_accepting_delegated_calls
):
    # Only accepting delegated calls opens this audience; acting for people does not.
    priv_pem, _ = _rsa_keypair
    with pytest.raises(HTTPException) as exc:
        oidc.decode_jwt(_addressed_to_the_delegation_audience_only(priv_pem))
    assert exc.value.status_code == 401


def test_strict_admits_the_delegation_audience_alone_when_accepting_delegated_calls(
    _rsa_keypair, accepting_delegated_calls
):
    priv_pem, _ = _rsa_keypair
    user = oidc.decode_jwt(_addressed_to_the_delegation_audience_only(priv_pem))
    assert user.client_id == "agentic"
    assert user.token_audiences == frozenset({"fred-delegation"})


def test_strict_accepts_the_realm_under_its_workload_address(monkeypatch, _rsa_keypair):
    internal = "http://keycloak.internal:8080/realms/app"
    monkeypatch.setattr(oidc, "_REALM_ISSUERS", frozenset({_REALM, internal}))
    priv_pem, _ = _rsa_keypair

    user = oidc.decode_jwt(_token(priv_pem, iss=internal, aud=_CLIENT, sub="svc-in"))

    assert user.token_issuer == internal
    with pytest.raises(HTTPException) as exc:
        oidc.decode_jwt(
            _token(priv_pem, iss="http://elsewhere/realms/app", aud=_CLIENT)
        )
    assert exc.value.status_code == 401


def test_strict_refuses_the_delegation_audience_to_a_listed_user_client(
    _rsa_keypair,
):
    priv_pem, _ = _rsa_keypair
    with delegation.preserved_delegation():
        delegation.initialize_delegation(
            DelegationConfig(accept_delegated_calls=True, user_clients=["portal"]),
            issuers=[_REALM],
            user_clients=[_CLIENT],
        )
        with pytest.raises(HTTPException) as exc:
            oidc.decode_jwt(
                _token(
                    priv_pem,
                    iss=_REALM,
                    aud="fred-delegation",
                    azp="portal",
                    resource_access=_CALLER_ROLE,
                )
            )
    assert exc.value.status_code == 401


def test_the_client_is_read_from_client_id_when_azp_is_absent(_rsa_keypair):
    priv_pem, _ = _rsa_keypair
    token = pyjwt.encode(
        {
            "iss": _REALM,
            "aud": _CLIENT,
            "sub": "svc-rfc9068",
            "client_id": "a-workload",
            "exp": int(time.time()) + 3600,
        },
        priv_pem,
        algorithm="RS256",
    )

    user = oidc.decode_jwt(token)

    assert user.client_id == "a-workload"
    assert user.token_type is None


def test_strict_refuses_a_user_client_named_only_in_client_id(
    _rsa_keypair, accepting_delegated_calls
):
    """The login-client guard reads the same client the principal does, azp or not."""
    priv_pem, _ = _rsa_keypair
    token = pyjwt.encode(
        {
            "iss": _REALM,
            "aud": "fred-delegation",
            "sub": "svc-no-azp",
            "client_id": _CLIENT,
            "resource_access": _CALLER_ROLE,
            "exp": int(time.time()) + 3600,
        },
        priv_pem,
        algorithm="RS256",
    )

    with pytest.raises(HTTPException) as exc:
        oidc.decode_jwt(token)
    assert exc.value.status_code == 401


def test_service_accounts_only_trusts_a_keycloak_service_account_token(_rsa_keypair):
    priv_pem, _ = _rsa_keypair
    with delegation.preserved_delegation():
        delegation.initialize_delegation(
            DelegationConfig(accept_delegated_calls=True, service_accounts_only=True),
            issuers=[_REALM],
            user_clients=[_CLIENT],
        )
        user = oidc.decode_jwt(
            _token(
                priv_pem,
                iss=_REALM,
                aud="fred-delegation",
                sub="svc-account",
                azp="agentic",
                preferred_username="service-account-agentic",
                client_id="agentic",
                resource_access=_CALLER_ROLE,
            )
        )

        assert user.service_account is True
        assert delegation.is_delegation_caller(user) is True
        assert "service_account" not in user.model_dump()
        assert "service_account" not in repr(user)


def test_service_accounts_only_refuses_a_persons_token_from_an_unlisted_client(
    _rsa_keypair,
):
    """The misgranted role and a client nobody listed: the option still refuses it."""
    priv_pem, _ = _rsa_keypair
    person = {
        "iss": _REALM,
        "azp": "unlisted-portal",
        "preferred_username": "alice",
        "resource_access": _CALLER_ROLE,
    }
    with delegation.preserved_delegation():
        delegation.initialize_delegation(
            DelegationConfig(accept_delegated_calls=True, service_accounts_only=True),
            issuers=[_REALM],
            user_clients=[_CLIENT],
        )
        with pytest.raises(HTTPException) as exc:
            oidc.decode_jwt(_token(priv_pem, aud="fred-delegation", **person))
        assert exc.value.status_code == 401

        # Addressed to this receiver too, it decodes but still cannot delegate.
        user = oidc.decode_jwt(
            _token(priv_pem, aud=[_CLIENT, "fred-delegation"], **person)
        )
        assert user.service_account is False
        assert delegation.is_delegation_caller(user) is False
