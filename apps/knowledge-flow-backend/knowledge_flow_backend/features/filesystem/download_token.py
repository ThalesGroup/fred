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
Signed, short-TTL tokens for the `/fs/download` route (FILES-04, RFC §7.3–§7.4).

An agent (or the chat) returns a deliverable as a clickable download link. The link is a
``/fs/download/{path}?token=…`` URL whose token is an HMAC-SHA256 signature binding the exact
``(path, uid, expiry)``. The download route verifies it before serving, so a link in chat
history is tamper-proof and expires on its own — while the file itself stays in the user's
space (the durable channel) and ``/fs/download`` still runs through the single ReBAC
enforcement point.

The signing key comes from ``KNOWLEDGE_FLOW_DOWNLOAD_SECRET`` (set in any real deployment); a
clearly-labelled development fallback keeps local runs working without configuration. The key
must be identical across replicas so a link minted by one instance verifies on another.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time

logger = logging.getLogger(__name__)

# 10 minutes: long enough to click a link in chat, short enough to bound exposure.
DEFAULT_DOWNLOAD_TTL_SECONDS = 600

_DEV_FALLBACK = "knowledge-flow-dev-download-signing-key"  # pragma: allowlist secret  # nosec B105


def _signing_key() -> bytes:
    configured = os.getenv("KNOWLEDGE_FLOW_DOWNLOAD_SECRET")
    if not configured:
        logger.warning("KNOWLEDGE_FLOW_DOWNLOAD_SECRET is not set; using the insecure development signing key. Set it in any real deployment.")
        configured = _DEV_FALLBACK
    return configured.encode("utf-8")


def _signature(payload: str) -> str:
    digest = hmac.new(_signing_key(), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def make_download_token(
    path: str,
    uid: str,
    *,
    ttl_seconds: int = DEFAULT_DOWNLOAD_TTL_SECONDS,
    now: int | None = None,
) -> str:
    """
    Mint a signed token for ``(path, uid)`` valid for ``ttl_seconds``.

    The token is ``{expiry}.{signature}``; the download route recomputes the signature from
    the URL path and the session uid, so neither can be altered after minting.
    """
    issued = int(time.time()) if now is None else now
    expiry = issued + ttl_seconds
    return f"{expiry}.{_signature(f'{path}|{uid}|{expiry}')}"


def verify_download_token(
    token: str,
    path: str,
    uid: str,
    *,
    now: int | None = None,
) -> bool:
    """Return True only if ``token`` was minted for this exact ``(path, uid)`` and is unexpired."""
    if not token:
        return False
    try:
        expiry_str, signature = token.split(".", 1)
        expiry = int(expiry_str)
    except (ValueError, AttributeError):
        return False
    current = int(time.time()) if now is None else now
    if current > expiry:
        return False
    expected = _signature(f"{path}|{uid}|{expiry}")
    return hmac.compare_digest(signature, expected)
