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

"""Unit tests for the keyless grant signer/verifier (RUNTIME-07 Phase 2a)."""

from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

from fred_core.security.keyless_signer import (
    ALGORITHM,
    GrantSigner,
    GrantVerifier,
    IamSignBlobSigner,
    LocalKeypairSigner,
    build_jwks,
    decode_signature,
    encode_signature,
    public_jwk_from_pem,
)

_KEY_ID = "cp-key-test-1"


def _rsa_private_pem() -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


@pytest.fixture
def signer() -> LocalKeypairSigner:
    return LocalKeypairSigner(_rsa_private_pem(), key_id=_KEY_ID)


@pytest.fixture
def verifier(signer: LocalKeypairSigner) -> GrantVerifier:
    return GrantVerifier.from_public_key_pem(signer.public_key_pem(), key_id=_KEY_ID)


def test_algorithm_is_rs256() -> None:
    assert ALGORITHM == "RS256"


def test_local_signer_satisfies_protocol(signer: LocalKeypairSigner) -> None:
    assert isinstance(signer, GrantSigner)
    assert signer.key_id == _KEY_ID


def test_sign_verify_roundtrip(
    signer: LocalKeypairSigner, verifier: GrantVerifier
) -> None:
    payload = b'{"agent_instance_id":"inst-42","team_id":"fredlab"}'
    sig = signer.sign(payload)
    assert verifier.verify(payload, sig, key_id=_KEY_ID) is True


def test_verify_rejects_tampered_payload(
    signer: LocalKeypairSigner, verifier: GrantVerifier
) -> None:
    payload = b'{"team_id":"fredlab"}'
    sig = signer.sign(payload)
    tampered = b'{"team_id":"intruder"}'
    assert verifier.verify(tampered, sig, key_id=_KEY_ID) is False


def test_verify_rejects_unknown_key_id(
    signer: LocalKeypairSigner, verifier: GrantVerifier
) -> None:
    payload = b"hello"
    sig = signer.sign(payload)
    assert verifier.verify(payload, sig, key_id="some-other-key") is False


def test_verify_rejects_signature_from_a_different_key(
    verifier: GrantVerifier,
) -> None:
    # A grant signed by an attacker's key, but claiming our key_id, must fail.
    rogue = LocalKeypairSigner(_rsa_private_pem(), key_id=_KEY_ID)
    payload = b"hello"
    rogue_sig = rogue.sign(payload)
    assert verifier.verify(payload, rogue_sig, key_id=_KEY_ID) is False


def test_signature_encode_decode_roundtrip(signer: LocalKeypairSigner) -> None:
    sig = signer.sign(b"payload")
    encoded = encode_signature(sig)
    assert isinstance(encoded, str)
    assert "=" not in encoded  # base64url, padding stripped
    assert decode_signature(encoded) == sig


def test_local_signer_rejects_non_rsa_key() -> None:
    ed_pem = ed25519.Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    with pytest.raises(ValueError, match="RSA"):
        LocalKeypairSigner(ed_pem, key_id=_KEY_ID)


def test_iam_sign_blob_signer_uses_client_and_pins_returned_key_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IamSignBlobSigner delegates to the GCP client and adopts the key id GCP
    reports for the actual signing key — verified without touching GCP."""
    captured: dict[str, object] = {}

    class _FakeClient:
        def sign_blob(self, request):
            captured["request"] = request
            return SimpleNamespace(signed_blob=b"gcp-signature", key_id="gcp-kid-9")

    signer = IamSignBlobSigner("sa@project.iam.gserviceaccount.com")
    monkeypatch.setattr(signer, "_ensure_client", lambda: _FakeClient())

    out = signer.sign(b"payload-bytes")

    assert out == b"gcp-signature"
    assert signer.key_id == "gcp-kid-9"  # pinned from the response
    assert captured["request"] == {
        "name": "projects/-/serviceAccounts/sa@project.iam.gserviceaccount.com",
        "payload": b"payload-bytes",
    }


def test_public_jwk_and_jwks_shape(signer: LocalKeypairSigner) -> None:
    jwk = public_jwk_from_pem(signer.public_key_pem(), key_id=_KEY_ID)
    assert jwk["kty"] == "RSA"
    assert jwk["kid"] == _KEY_ID
    assert jwk["alg"] == "RS256"
    assert jwk["use"] == "sig"
    assert "n" in jwk and "e" in jwk  # public RSA params, no private 'd'
    assert "d" not in jwk

    jwks = build_jwks(signer.public_key_pem(), key_id=_KEY_ID)
    assert jwks["keys"] == [jwk]


def test_verifier_from_jwks_roundtrip(signer: LocalKeypairSigner) -> None:
    """The runtime path: build a verifier from the published JWKS and verify."""
    jwks = build_jwks(signer.public_key_pem(), key_id=_KEY_ID)
    verifier = GrantVerifier.from_jwks(jwks)

    payload = b'{"agent_instance_id":"inst-42"}'
    sig = signer.sign(payload)
    assert verifier.verify(payload, sig, key_id=_KEY_ID) is True
    assert verifier.verify(payload, sig, key_id="unknown") is False
