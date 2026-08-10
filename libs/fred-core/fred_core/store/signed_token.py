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

"""Stateless HMAC tokens binding a short-lived capability to a fixed set of components.

Why this exists:
- Two features need the same primitive: knowledge-flow's `/fs/download` links
  (bound to `path|uid`) and the application-signed object proxy URLs described in
  `docs/swift/rfc/CONTENT-URL-STRATEGY-RFC.md` (bound to the object key alone).
  Callers choose what is bound; the token format is identical.
- The token is stateless: the expiry travels inside it and is only trustworthy
  because the signature covers it.

How to use it:
- Mint with `make_signed_token([...components...], secret=..., ttl_seconds=...)`.
- Verify with `verify_signed_token(token, [...same components...], secret=...)`.
- Read the per-app signing key with `read_signing_secret("MY_APP_SECRET")`; it
  raises when unset rather than falling back to a shipped default key.

Example:
```python
secret = read_signing_secret("KNOWLEDGE_FLOW_CONTENT_URL_SECRET")
token = make_signed_token(["doc-1/output/media/img.png"], secret=secret, ttl_seconds=60)
verify_signed_token(token, ["doc-1/output/media/img.png"], secret=secret)  # True
```

Never log a token or a URL containing one: it *is* the capability.

Note on the payload: components are joined with `|`, a format inherited from the
already-minted `/fs/download` links this helper must keep verifying. It is therefore
not self-delimiting — every caller of a given token family must always bind the same
number of components, which is the case here (`/fs/download` binds two, the object
proxy binds one).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from collections.abc import Sequence

# Default location documented in every app's `config/.env.template`.
DEFAULT_ENV_FILE = "config/.env"


class MissingSigningSecretError(RuntimeError):
    """Raised when the signing key an app needs is not configured.

    Why this exists:
    - A signed URL is a bearer capability, so there is no safe default key to
      fall back to. Startup (or the first mint) must stop with a message naming
      both the variable and the file to set it in.
    """


def read_signing_secret(env_var: str, *, env_file: str = DEFAULT_ENV_FILE) -> str:
    """Return the signing key from `env_var`, or raise an actionable error.

    Why this exists:
    - Signing keys are per-app on purpose: a knowledge-flow token must never
      verify against a control-plane object.

    Example:
    ```python
    secret = read_signing_secret("CONTROL_PLANE_CONTENT_URL_SECRET")
    ```
    """

    configured = os.getenv(env_var)
    if not configured:
        raise MissingSigningSecretError(
            f"{env_var} is not set. Signed URLs are bearer capabilities, so there is no "
            f"default key. Generate one (`openssl rand -hex 32`) and set {env_var} in "
            f"{env_file} (documented in {env_file}.template). The same value must be used "
            "by every replica of this application."
        )
    return configured


def _payload(components: Sequence[str], expiry: int) -> str:
    """Build the exact string covered by the signature: `c1|c2|…|expiry`."""

    return "|".join([*components, str(expiry)])


def _signature(components: Sequence[str], expiry: int, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        _payload(components, expiry).encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def make_signed_token(
    components: Sequence[str],
    *,
    secret: str,
    ttl_seconds: int,
    now: int | None = None,
) -> str:
    """Mint `{expiry}.{signature}` binding `components` for `ttl_seconds`.

    Example:
    ```python
    make_signed_token(["a/b.png"], secret=secret, ttl_seconds=60)
    ```
    """

    issued = int(time.time()) if now is None else now
    expiry = issued + ttl_seconds
    return f"{expiry}.{_signature(components, expiry, secret)}"


def verify_signed_token(
    token: str,
    components: Sequence[str],
    *,
    secret: str,
    now: int | None = None,
) -> bool:
    """Return True only if `token` was minted for exactly `components` and is unexpired."""

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
    return hmac.compare_digest(signature, _signature(components, expiry, secret))


def token_expiry(token: str) -> int | None:
    """Return the expiry epoch carried by `token`, or None when unparseable.

    Why this exists:
    - The object proxy caps `Cache-Control: max-age` at the remaining lifetime of
      the capability, so a cached response never outlives the token that fetched it.
    """

    if not token:
        return None
    try:
        return int(token.split(".", 1)[0])
    except (ValueError, AttributeError):
        return None
