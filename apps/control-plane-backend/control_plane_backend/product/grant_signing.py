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
Control-plane grant signer wiring (RUNTIME-07 Phase 2b).

Builds the configured ``GrantSigner`` and exposes the public JWKS so the runtime
can verify autonomously. The primary, first-tested backend is ``kind="local"``
(an RSA private key the control-plane mounts) + a control-plane-served JWKS — this
works fully offline (local Docker: Keycloak + SeaweedFS, or any non-GCP on-prem).
``kind="gcp"`` uses IAM signBlob and the service account's Google-published JWKS.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fred_core.security.keyless_signer import (
    GrantSigner,
    IamSignBlobSigner,
    LocalKeypairSigner,
    build_jwks,
)
from fred_core.security.structure import GrantSigningConfig

logger = logging.getLogger(__name__)


def _load_local_private_key_pem(cfg: GrantSigningConfig) -> bytes:
    """Read the local RSA private key from a mounted file or an env var."""
    if cfg.private_key_path:
        return Path(cfg.private_key_path).read_bytes()
    pem = os.getenv(cfg.private_key_env_var)
    if not pem:
        raise ValueError(
            "grant_signing.kind='local' requires an RSA private key: set "
            f"${cfg.private_key_env_var} or grant_signing.private_key_path."
        )
    return pem.encode("utf-8")


def build_grant_signer(cfg: GrantSigningConfig | None) -> GrantSigner | None:
    """
    Build the configured signer, or None when signing is disabled.

    Raises ValueError on a misconfigured-but-enabled signer so a deployment fails
    fast at issuance rather than silently emitting unsigned grants.
    """
    if cfg is None or not cfg.enabled:
        return None
    if cfg.kind == "local":
        return LocalKeypairSigner(_load_local_private_key_pem(cfg), key_id=cfg.key_id)
    if cfg.kind == "gcp":
        if not cfg.signing_service_account_email:
            raise ValueError(
                "grant_signing.kind='gcp' requires signing_service_account_email."
            )
        return IamSignBlobSigner(cfg.signing_service_account_email, key_id=cfg.key_id)
    raise ValueError(f"Unknown grant_signing.kind: {cfg.kind!r}")


def grant_signing_jwks(cfg: GrantSigningConfig | None) -> dict[str, Any]:
    """
    Public JWKS the runtime fetches to verify grant signatures.

    For the local signer this is derived from the configured private key. For the
    GCP signer the runtime uses Google's published JWKS directly, so this endpoint
    returns an empty key set.
    """
    empty: dict[str, Any] = {"keys": []}
    if cfg is None or not cfg.enabled or cfg.kind != "local":
        return empty
    signer = build_grant_signer(cfg)
    if not isinstance(
        signer, LocalKeypairSigner
    ):  # pragma: no cover - kind guard above
        return empty
    return build_jwks(signer.public_key_pem(), key_id=cfg.key_id)
