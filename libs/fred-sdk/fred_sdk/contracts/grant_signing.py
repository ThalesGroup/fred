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
Sign and verify an ``ExecutionGrant`` (RUNTIME-07 Phase 2).

This is the glue between the grant *contract* (``fred-sdk``) and the keyless
*signer* (``fred-core``). It lives in ``fred-sdk`` because this is the only layer
that depends on BOTH the ``ExecutionGrant`` model and ``fred_core``'s signer —
``fred-core`` must not depend on ``fred-sdk``.

- Control-plane calls :func:`sign_grant` at ``prepare-execution`` (after ReBAC),
  once per grant.
- The runtime calls :func:`verify_grant_signature` to verify autonomously, with
  only the control-plane public key — no callback.

The signature is detached and covers :meth:`ExecutionGrant.canonical_payload`
(every field except ``signature``), so ``key_id`` and ``jti`` are themselves
signed. ``sign_grant`` therefore sets ``key_id``/``jti`` BEFORE computing the
payload, then attaches the signature last.
"""

from __future__ import annotations

import uuid

from fred_core.security.keyless_signer import (
    GrantSigner,
    GrantVerifier,
    decode_signature,
    encode_signature,
)

from .execution import ExecutionGrant


def sign_grant(
    grant: ExecutionGrant,
    signer: GrantSigner,
    *,
    jti: str | None = None,
) -> ExecutionGrant:
    """
    Return a signed copy of ``grant``.

    Sets ``key_id`` (from the signer) and ``jti`` (generated when absent), signs
    ``canonical_payload()``, and attaches the base64url signature. Any signature
    already present is cleared first — a grant is signed exactly once, by
    control-plane.
    """
    base = grant.model_copy(
        update={
            "key_id": signer.key_id,
            "jti": jti or grant.jti or uuid.uuid4().hex,
            "signature": None,
        }
    )
    signature = signer.sign(base.canonical_payload())
    return base.model_copy(update={"signature": encode_signature(signature)})


def verify_grant_signature(grant: ExecutionGrant, verifier: GrantVerifier) -> bool:
    """
    Return True iff ``grant`` carries a valid signature over its canonical payload.

    Returns False for an unsigned grant, an unknown ``key_id``, or a signature
    that does not match — the caller maps False to an authorization failure (or,
    in observe mode, logs and continues).
    """
    if not grant.is_signed():
        return False
    signature = grant.signature
    key_id = grant.key_id
    if signature is None or key_id is None:  # pragma: no cover - is_signed covers this
        return False
    return verifier.verify(
        grant.canonical_payload(), decode_signature(signature), key_id
    )
