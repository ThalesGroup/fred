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

"""Browser-facing object URLs: real presigned URL, or application-signed proxy URL.

Why this exists:
- Presigned URLs only work on MinIO/S3 and on GCS deployments that hold
  `iam.serviceAccounts.signBlob`. Everywhere else (GCS without a signing service
  account, local filesystem) the browser cannot fetch an object at all.
- `docs/swift/rfc/CONTENT-URL-STRATEGY-RFC.md` replaces the presigned URL with an
  application-signed URL pointing at a minimal read-through proxy in front of the
  content store the app already has. Both modes are time-limited bearer
  capabilities over one object key, so consumers cannot tell them apart.

Invariant (unchanged from the one already governing `get_presigned_url`):

> Only call the resolver after the caller has authorized the user for that object.

How to use it:
```python
resolver = ContentUrlResolver(
    strategy="proxy",
    store=content_store,
    base_url="/knowledge-flow/v1",
    secret=read_signing_secret("KNOWLEDGE_FLOW_CONTENT_URL_SECRET"),
)
url = resolver.url_for("doc-1/output/media/img.png", expires=timedelta(minutes=1))
```

Never log the returned URL: in both modes it carries a credential.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Literal, Protocol
from urllib.parse import quote

from fred_core.store.signed_token import make_signed_token

ContentUrlStrategy = Literal["presigned", "proxy"]

# Path segment of the object proxy, shared by the resolver (which mints URLs) and
# the router factory (which serves them) so the two can never drift.
OBJECT_PROXY_PATH = "/objects"


class PresignedUrlSource(Protocol):
    """The single store capability the `presigned` strategy needs."""

    def get_presigned_url(
        self, key: str, expires: timedelta = timedelta(hours=1)
    ) -> str: ...


class ContentUrlResolver:
    """Return a temporary browser-facing URL for an object key, per configured strategy.

    Why this is a standalone service and not a mixin on the store classes
    (RFC §6.1): the repo has two independent store families (`fred_core.store.
    ContentStore` and knowledge-flow's `BaseContentStore` ABC). Wiring strategy,
    secret and public base URL into six store constructors would redefine "content
    store" as something that also mints capability tokens. This class is purely
    additive and touches neither hierarchy.
    """

    def __init__(
        self,
        *,
        strategy: ContentUrlStrategy,
        store: PresignedUrlSource,
        base_url: str,
        secret: str | None = None,
    ) -> None:
        """Bind a strategy to the store it resolves against.

        `base_url` is the application's API prefix (e.g. `/knowledge-flow/v1`);
        proxy URLs are same-origin, exactly like the media URLs they replace.
        `secret` is required in `proxy` mode only.
        """

        if strategy == "proxy" and not secret:
            raise ValueError(
                "ContentUrlResolver requires a signing secret when strategy='proxy'"
            )
        self.strategy = strategy
        self.store = store
        self.base_url = base_url.rstrip("/")
        self.secret = secret

    def url_for(self, key: str, *, expires: timedelta) -> str:
        """Return a URL granting read access to `key` for `expires`.

        Example:
        ```python
        resolver.url_for("teams/t1/banner.png", expires=timedelta(seconds=60))
        ```
        """

        if self.strategy == "presigned":
            return self.store.get_presigned_url(key, expires=expires)

        secret = self.secret
        if not secret:  # unreachable: __init__ rejects proxy mode without a secret
            raise ValueError(
                "ContentUrlResolver requires a signing secret when strategy='proxy'"
            )
        ttl_seconds = max(int(expires.total_seconds()), 1)
        token = make_signed_token([key], secret=secret, ttl_seconds=ttl_seconds)
        # Raw key on purpose (RFC §6.4): the signature makes tampering ineffective,
        # and the key is already visible in today's same-origin media URLs.
        return f"{self.base_url}{OBJECT_PROXY_PATH}/{quote(key.lstrip('/'), safe='/')}?token={token}"
