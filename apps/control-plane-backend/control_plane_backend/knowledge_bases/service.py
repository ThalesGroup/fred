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
Knowledge Base definitions: publication by their own image, and Platform Admin
enablement over what was published.

Listing never reaches a pod and never reports availability — a stored
declaration says an image was deployed, not that a worker is running.
Enablement writes the same tuples capability and application enablement write,
through the shared operation in `capabilities.enablement`; this module adds no
second enablement mechanism.
"""

from __future__ import annotations

import logging

from fred_core import KeycloakUser, prefix_covers
from fred_core.security.structure import LOCAL_DEV_CLIENT_ID, is_service_agent
from fred_sdk.knowledge_base import KnowledgeBaseDeclaration

from control_plane_backend.knowledge_bases.schemas import (
    KnowledgeBasePublicationResult,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies

logger = logging.getLogger(__name__)


class KnowledgeBaseClientMismatch(Exception):
    """Raised when a client publishes a definition bound to a different one."""

    http_status = 403


async def publish_definition(
    *,
    user: KeycloakUser,
    prefix: str,
    declaration: KnowledgeBaseDeclaration,
    deps: ProductServiceDependencies,
) -> KnowledgeBasePublicationResult:
    """Record what an image declares about itself, at deployment time.

    A contributor owns a prefix and publishes as many names under it as it
    wants. The first publication claims that prefix for the calling client;
    every later one must present the same client, so nobody writes under
    another's prefix. The claim itself is enforced in the store, by a row whose
    primary key is the prefix — checking it here would be racy.
    """

    # A workload identity, not a person: without this an ordinary signed-in
    # user's token carries the frontend's `azp` and could publish definitions.
    # The local-dev client is admitted here and ONLY here — a targeted
    # allowance, so that authentication being disabled never turns every local
    # caller into a service identity platform-wide.
    if not is_service_agent(user) and user.client_id != LOCAL_DEV_CLIENT_ID:
        raise KnowledgeBaseClientMismatch(
            "Publishing requires a service identity, not a user session"
        )
    caller = user.client_id
    if not caller:
        raise KnowledgeBaseClientMismatch(
            "Publishing requires a confidential client identity"
        )

    if not prefix_covers(prefix, declaration.id):
        raise KnowledgeBaseClientMismatch(
            f"{declaration.id!r} is not under the declared prefix {prefix!r}"
        )

    published = await deps.get_knowledge_base_definition_store().upsert(
        prefix=prefix, declaration=declaration, client_id=caller
    )
    logger.info(
        "[knowledge-base-publication] stored declaration for %s version %s",
        published.id,
        published.version,
    )
    return KnowledgeBasePublicationResult(
        id=published.id, prefix=published.prefix, version=published.version
    )
