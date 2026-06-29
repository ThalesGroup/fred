# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""Strict JWT validation under the C3 profile (RUNTIME-07 rev. 2, finding F-E).

When STRICT_ISSUER / STRICT_AUDIENCE are set, decode_jwt must enforce EXACT issuer
and audience on the signature-verified payload (PyJWT verify_aud=True), not a
prefix/peek check. These tests sign real RS256 tokens and mock only the JWKS key
resolution.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from fred_core.security import oidc

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
    monkeypatch.setattr(oidc, "STRICT_ISSUER", True)
    monkeypatch.setattr(oidc, "STRICT_AUDIENCE", True)
    monkeypatch.setattr(
        oidc,
        "_get_jwks_client",
        lambda: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public_key)
        ),
    )


def _token(priv_pem: bytes, *, iss: str, aud: str, sub: str = "u-1") -> str:
    return pyjwt.encode(
        {
            "iss": iss,
            "aud": aud,
            "sub": sub,
            "preferred_username": "alice",
            "exp": int(time.time()) + 3600,
        },
        priv_pem,
        algorithm="RS256",
    )


def test_strict_accepts_exact_issuer_and_audience(_rsa_keypair):
    priv_pem, _ = _rsa_keypair
    user = oidc.decode_jwt(_token(priv_pem, iss=_REALM, aud=_CLIENT))
    assert user.uid == "u-1"


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
