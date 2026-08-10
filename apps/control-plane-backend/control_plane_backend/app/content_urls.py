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

"""One place that reads `content_storage.url_strategy` into a `ContentUrlResolver`.

Why this exists:
- The application container and the team service both need the resolver, and a
  second independently derived view of the same setting is exactly how a
  "the app offered this, then rejected it" mismatch appears. One factory, one
  reading of the config.
"""

from __future__ import annotations

from fred_core.store import ContentStore, ContentUrlResolver, read_signing_secret

from control_plane_backend.config.models import Configuration

# Signing key for application-signed object URLs (content_storage.url_strategy=proxy).
# Per-app on purpose: a control-plane token must never verify against knowledge-flow
# objects. Documented in config/.env.template.
CONTENT_URL_SECRET_ENV = "CONTROL_PLANE_CONTENT_URL_SECRET"  # nosec B105  # pragma: allowlist secret


def build_content_url_resolver(
    configuration: Configuration, store: ContentStore
) -> ContentUrlResolver:
    """Return the resolver matching the configured `content_storage.url_strategy`.

    Raises `MissingSigningSecretError` when the strategy is `proxy` and no signing
    key is configured for this application.
    """

    strategy = configuration.storage.content_storage.url_strategy
    return ContentUrlResolver(
        strategy=strategy,
        store=store,
        base_url=configuration.app.base_url,
        secret=read_signing_secret(CONTENT_URL_SECRET_ENV)
        if strategy == "proxy"
        else None,
    )
