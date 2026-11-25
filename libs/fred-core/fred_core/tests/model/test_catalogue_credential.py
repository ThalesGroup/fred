# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import base64

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fred_core.model.credentials import catalogue_credential


def envelope(monkeypatch):
    key = bytes(range(32))
    monkeypatch.setenv("MODEL_CATALOG_ENCRYPTION_KEY", base64.b64encode(key).decode())
    nonce = bytes(range(12))
    sealed = nonce + AESGCM(key).encrypt(
        nonce, b"synthetic-provider-token", b"catalog-a\nhttps://models.invalid/v1"
    )
    return base64.encodebytes(sealed).decode()


def test_destination_bound_envelope_accepts_postgres_line_breaks(monkeypatch):
    value = catalogue_credential(
        envelope(monkeypatch), "catalog-a", "https://models.invalid/v1"
    )
    assert value is not None
    assert value.get_secret_value() == "synthetic-provider-token"
    assert "synthetic-provider-token" not in repr(value)
    assert catalogue_credential(None, "legacy", "https://legacy.invalid") is None


@pytest.mark.parametrize(
    "source,root",
    [
        ("catalog-b", "https://models.invalid/v1"),
        ("catalog-a", "https://other.invalid/v1"),
    ],
)
def test_cannot_reuse_envelope_for_another_source_or_destination(
    monkeypatch, source, root
):
    with pytest.raises(ValueError, match="admitted destination") as error:
        catalogue_credential(envelope(monkeypatch), source, root)
    assert "synthetic-provider-token" not in str(error.value)


@pytest.mark.parametrize(
    "fault", ["missing_key", "wrong_key", "truncated", "malformed", "modified"]
)
def test_unreadable_credentials_fail_without_exposing_values(monkeypatch, fault):
    value = envelope(monkeypatch)
    if fault == "missing_key":
        monkeypatch.delenv("MODEL_CATALOG_ENCRYPTION_KEY")
    elif fault == "wrong_key":
        monkeypatch.setenv(
            "MODEL_CATALOG_ENCRYPTION_KEY", base64.b64encode(b"x" * 32).decode()
        )
    elif fault == "truncated":
        value = base64.b64encode(b"short").decode()
    elif fault == "modified":
        raw = bytearray(base64.b64decode(value))
        raw[-1] ^= 1
        value = base64.b64encode(raw).decode()
    else:
        value = "!invalid!"
    with pytest.raises(ValueError, match="unavailable"):
        catalogue_credential(value, "catalog-a", "https://models.invalid/v1")
