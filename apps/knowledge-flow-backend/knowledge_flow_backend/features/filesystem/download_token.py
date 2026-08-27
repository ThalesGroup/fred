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

This module is a thin binding over :mod:`fred_core.store.signed_token`, which is shared with
the application-signed object proxy (``docs/swift/rfc/CONTENT-URL-STRATEGY-RFC.md``). Only the
bound components differ — ``path|uid`` here, the object key there — so the wire format of
already-minted links is unchanged.

The signing key comes from ``KNOWLEDGE_FLOW_DOWNLOAD_SECRET``. There is no development
fallback: a hardcoded signing key in shipped source is dangerous whatever route consumes it
(RFC §6.2), so an unset variable raises with the file to set it in.
"""

from __future__ import annotations

import logging

from fred_core.store.signed_token import (
    make_signed_token,
    read_signing_secret,
    verify_signed_token,
)

logger = logging.getLogger(__name__)

# 10 minutes: long enough to click a link in chat, short enough to bound exposure.
DEFAULT_DOWNLOAD_TTL_SECONDS = 600

# Name of the variable, not a secret.
DOWNLOAD_SECRET_ENV = "KNOWLEDGE_FLOW_DOWNLOAD_SECRET"  # nosec B105  # pragma: allowlist secret


def _signing_key() -> str:
    """Return the configured signing key, or raise naming the variable and the file."""

    return read_signing_secret(DOWNLOAD_SECRET_ENV)


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
    return make_signed_token([path, uid], secret=_signing_key(), ttl_seconds=ttl_seconds, now=now)


def verify_download_token(
    token: str,
    path: str,
    uid: str,
    *,
    now: int | None = None,
) -> bool:
    """Return True only if ``token`` was minted for this exact ``(path, uid)`` and is unexpired."""
    return verify_signed_token(token, [path, uid], secret=_signing_key(), now=now)
