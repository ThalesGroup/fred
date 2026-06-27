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

"""
Asymmetric signing/verification for ExecutionGrant payloads (RUNTIME-07).

Why this module exists
----------------------
The control-plane must be able to sign a short-lived grant ONCE, and any
fred-agents runtime pod must be able to verify it autonomously — with no
call back to the control-plane per turn. This is the "valet key" / signed-URL
pattern, the same asymmetric model the platform already uses for Keycloak JWTs:
the signer holds a PRIVATE key, every verifier holds only the PUBLIC key.

Design
------
- Asymmetric only. A runtime pod is internet-facing; it must be able to VERIFY
  but never MINT a grant. So the private key lives only on the signer side.
- Algorithm is RS256 (RSASSA-PKCS1-v1.5 + SHA-256). This matches both GCP IAM
  ``signBlob`` (service-account keys are RSA) and the JWKS ecosystem the runtime
  already speaks via ``oidc.py``.
- The signature is DETACHED: it covers ``ExecutionGrant.canonical_payload()``
  (every grant field except ``signature``). The grant stays a typed object the
  runtime can read directly; only the signature travels alongside.

What lives here
---------------
- ``GrantSigner`` protocol with two implementations:
  - ``LocalKeypairSigner``  — signs in-process from a PEM private key (a K8s
    Secret on-prem). No external call.
  - ``IamSignBlobSigner``   — asks GCP IAM to sign under Workload Identity; the
    private key never leaves GCP (reuses the FILES-06 keyless pattern).
- ``GrantVerifier`` — verifies a detached signature against a public key chosen
  by ``key_id``. Build it from explicit public keys (tests / on-prem) or, later,
  from a JWKS URL (added in Phase 2c).

This module signs/verifies raw ``bytes`` only. The grant-specific glue (compute
``canonical_payload()`` → sign → set ``signature``/``key_id``) lives where both
``fred-sdk`` and a signer are available (control-plane issuance, runtime verify),
because ``fred-core`` must not depend on ``fred-sdk``.
"""

from __future__ import annotations

import base64
from typing import Mapping, Protocol, runtime_checkable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

# RSASSA-PKCS1-v1.5 with SHA-256 — compatible with GCP signBlob and JWKS RS256.
ALGORITHM = "RS256"


def encode_signature(signature: bytes) -> str:
    """Base64url-encode a raw signature for transport in the grant (no padding)."""
    return base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")


def decode_signature(encoded: str) -> bytes:
    """Inverse of :func:`encode_signature`; tolerant of missing padding."""
    pad = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + pad)


@runtime_checkable
class GrantSigner(Protocol):
    """A signer that produces an RS256 signature over arbitrary bytes."""

    @property
    def key_id(self) -> str:
        """Identifier of the signing key, embedded in the grant for verifier lookup."""
        ...

    def sign(self, payload: bytes) -> bytes:
        """Return the raw signature bytes over ``payload``."""
        ...


class LocalKeypairSigner:
    """
    In-process RS256 signer from a PEM RSA private key (on-prem / non-GCP).

    Why: signs locally with no external call — the fast path when an extra GCP
    round-trip per issuance is undesirable. The private key is a K8s Secret the
    control-plane mounts; runtimes never hold it.
    """

    def __init__(self, private_key_pem: bytes, key_id: str) -> None:
        loaded = serialization.load_pem_private_key(private_key_pem, password=None)
        if not isinstance(loaded, RSAPrivateKey):
            raise ValueError("LocalKeypairSigner requires an RSA private key (RS256).")
        self._key: RSAPrivateKey = loaded
        self._key_id = key_id

    @property
    def key_id(self) -> str:
        return self._key_id

    def sign(self, payload: bytes) -> bytes:
        return self._key.sign(payload, padding.PKCS1v15(), hashes.SHA256())

    def public_key_pem(self) -> bytes:
        """Export the matching public key (PEM) — e.g. to publish at a JWKS endpoint."""
        return self._key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )


class IamSignBlobSigner:
    """
    Keyless RS256 signer via GCP IAM ``signBlob`` (Workload Identity).

    The private key lives in GCP and never reaches this process — the same
    trust/ops model already approved for FILES-06 GCS signed URLs. Verification
    is likewise keyless: the runtime fetches the service account's
    Google-published JWKS.

    Note: signing an arbitrary blob uses ``google-cloud-iam-credentials`` —
    a DIFFERENT API than the ``google-cloud-storage`` URL signing in FILES-06.
    The dependency is imported lazily so this module loads without it (the GCP
    libs are only needed where this signer is actually constructed).
    """

    def __init__(self, service_account_email: str, key_id: str | None = None) -> None:
        self._sa_email = service_account_email
        # signBlob returns the signing key id; callers may also pin one.
        self._key_id = key_id or service_account_email
        self._client = None  # lazily created

    @property
    def key_id(self) -> str:
        return self._key_id

    def _ensure_client(self):
        if self._client is None:
            # Lazy import: only required where GCP signing is actually used.
            from google.cloud import iam_credentials_v1  # type: ignore[import-untyped]

            self._client = iam_credentials_v1.IAMCredentialsClient()
        return self._client

    def sign(self, payload: bytes) -> bytes:
        client = self._ensure_client()
        name = f"projects/-/serviceAccounts/{self._sa_email}"
        response = client.sign_blob(request={"name": name, "payload": payload})
        # Pin the actual signing key id returned by GCP for verifier lookup.
        if getattr(response, "key_id", None):
            self._key_id = response.key_id
        return response.signed_blob


class GrantVerifier:
    """
    Verifies a detached RS256 signature against a public key chosen by ``key_id``.

    Build it from explicit public keys (tests, on-prem mounts). A JWKS-backed
    constructor (Google SA JWKS or a control-plane-served JWKS) is added in
    Phase 2c, reusing the ``oidc.py`` ``PyJWKClient`` infrastructure.
    """

    def __init__(self, public_keys: Mapping[str, RSAPublicKey]) -> None:
        self._public_keys = dict(public_keys)

    @classmethod
    def from_public_key_pem(cls, public_key_pem: bytes, key_id: str) -> "GrantVerifier":
        loaded = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(loaded, RSAPublicKey):
            raise ValueError("GrantVerifier requires an RSA public key (RS256).")
        return cls({key_id: loaded})

    def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
        """Return True iff ``signature`` over ``payload`` is valid for ``key_id``."""
        public_key = self._public_keys.get(key_id)
        if public_key is None:
            return False
        try:
            public_key.verify(signature, payload, padding.PKCS1v15(), hashes.SHA256())
            return True
        except InvalidSignature:
            return False
