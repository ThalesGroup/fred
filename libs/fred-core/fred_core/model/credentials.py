# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Open an organization catalogue credential only for its admitted destination.

The deployment key is shared by the Control Plane and trusted inference workloads.
Provider tokens stay encrypted in SQL and in private worker/admission contracts.
This resolves a credential; it performs no authorization or admission refresh.
"""

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr


def catalogue_credential(
    envelope: str | None, source_id: str, api_root: str
) -> SecretStr | None:
    if envelope is None:
        return None
    try:
        key = base64.b64decode(
            os.environ["MODEL_CATALOG_ENCRYPTION_KEY"], validate=True
        )
        # PostgreSQL encode(base64) can insert line breaks in its private view.
        payload = base64.b64decode("".join(envelope.split()), validate=True)
        if len(key) != 32 or len(payload) < 28:
            raise ValueError("Invalid credential envelope")
        value = (
            AESGCM(key)
            .decrypt(payload[:12], payload[12:], f"{source_id}\n{api_root}".encode())
            .decode()
        )
        if not value:
            raise ValueError("Empty credential")
        return SecretStr(value)
    except (KeyError, ValueError, InvalidTag, binascii.Error):
        raise ValueError(
            "Catalogue inference credential is unavailable or does not match the admitted destination"
        ) from None
