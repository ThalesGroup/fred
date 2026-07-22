# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""Application-side ceiling on JWT lifetime (`MAX_TOKEN_LIFETIME_SECONDS`).

`decode_jwt`'s `verify_exp` only rejects a token that has already expired; it
never checked how long a token was *issued* to live in the first place, so a
misconfigured or unfamiliar IdP handing out multi-hour tokens would be
trusted without complaint. This is independent of STRICT_ISSUER/STRICT_AUDIENCE
(c3-gated) — it stays on by default, since Fred's own M2M provider already
mints short-lived, auto-refreshed tokens and is unaffected by it.
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
def _keycloak_enabled(monkeypatch, _rsa_keypair):
    _, public_key = _rsa_keypair
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "KEYCLOAK_URL", _REALM)
    monkeypatch.setattr(oidc, "KEYCLOAK_CLIENT_ID", _CLIENT)
    monkeypatch.setattr(
        oidc,
        "_get_jwks_client",
        lambda: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public_key)
        ),
    )


def _token(priv_pem: bytes, *, iat: int, exp: int, sub: str) -> str:
    return pyjwt.encode(
        {
            "iss": _REALM,
            "aud": _CLIENT,
            "sub": sub,
            "preferred_username": "alice",
            "iat": iat,
            "exp": exp,
        },
        priv_pem,
        algorithm="RS256",
    )


def test_token_within_lifetime_ceiling_is_accepted(_rsa_keypair):
    priv_pem, _ = _rsa_keypair
    now = int(time.time())
    token = _token(priv_pem, iat=now, exp=now + 300, sub="u-1")  # 5 min, well under 1h
    user = oidc.decode_jwt(token)
    assert user.uid == "u-1"


def test_token_exceeding_lifetime_ceiling_is_rejected(_rsa_keypair):
    priv_pem, _ = _rsa_keypair
    now = int(time.time())
    token = _token(priv_pem, iat=now, exp=now + 7200, sub="u-2")  # 2 hours
    with pytest.raises(HTTPException) as exc:
        oidc.decode_jwt(token)
    assert exc.value.status_code == 401
    assert "lifetime" in exc.value.detail.lower()


def test_token_with_exp_before_iat_is_rejected(monkeypatch, _rsa_keypair):
    """A malformed/confused-IdP token can claim iat after its own exp while
    exp is still in the future — `verify_exp` alone would accept it, and the
    ">" ceiling check silently passes a negative lifetime. Must be rejected
    explicitly rather than falling through.

    PyJWT itself rejects any iat beyond `leeway` in the future ("not yet
    valid"), which would normally catch this first — so this needs a
    positive `FRED_JWT_CLOCK_SKEW` (a real, supported deployment knob) to
    construct an iat PyJWT tolerates while still exceeding exp.
    """
    priv_pem, _ = _rsa_keypair
    monkeypatch.setattr(oidc, "CLOCK_SKEW_SECONDS", 60)
    now = int(time.time())
    token = _token(priv_pem, iat=now + 30, exp=now + 10, sub="u-5")
    with pytest.raises(HTTPException) as exc:
        oidc.decode_jwt(token)
    assert exc.value.status_code == 401
    assert "iat" in exc.value.detail.lower() or "exp" in exc.value.detail.lower()


def test_token_without_iat_claim_is_not_checked(_rsa_keypair):
    """Some tokens omit `iat`; the ceiling check is skipped rather than
    guessing — `verify_exp` above still governs plain expiry."""
    priv_pem, _ = _rsa_keypair
    now = int(time.time())
    token = pyjwt.encode(
        {
            "iss": _REALM,
            "aud": _CLIENT,
            "sub": "u-3",
            "preferred_username": "alice",
            "exp": now + 7200,
        },
        priv_pem,
        algorithm="RS256",
    )
    user = oidc.decode_jwt(token)
    assert user.uid == "u-3"


def test_lifetime_ceiling_is_configurable_via_env(monkeypatch, _rsa_keypair):
    priv_pem, _ = _rsa_keypair
    monkeypatch.setattr(oidc, "MAX_TOKEN_LIFETIME_SECONDS", 60)
    now = int(time.time())
    token = _token(priv_pem, iat=now, exp=now + 300, sub="u-4")  # 5 min > 60s ceiling
    with pytest.raises(HTTPException) as exc:
        oidc.decode_jwt(token)
    assert exc.value.status_code == 401
