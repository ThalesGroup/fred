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
Knowledge Base publication: the one write a definition's own image performs.

Admin visibility and team enablement are NOT here. A published definition is
projected into the shared capability catalog as `kind="knowledge_base"` and
managed through the capability admin routes, exactly as an application is —
one surface, while the grant still lands on the `knowledge_base_definition`
ReBAC type. Publication is gated on the exact client bound to the definition,
never on a broad service role.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from fred_core import KeycloakUser, get_current_user_without_gcu
from fred_core.security.models import AuthorizationError
from fred_sdk.knowledge_base import (
    KNOWLEDGE_BASE_ID_PATTERN,
    KnowledgeBaseDeclaration,
)
from pydantic import ValidationError

from control_plane_backend.app.route_errors import map_error as _map_error
from control_plane_backend.knowledge_bases import service as knowledge_base_service
from control_plane_backend.knowledge_bases.schemas import (
    KnowledgeBasePublicationRequest,
    KnowledgeBasePublicationResult,
)
from control_plane_backend.knowledge_bases.service import (
    KnowledgeBaseClientMismatch,
)
from control_plane_backend.knowledge_bases.store import KnowledgeBaseProviderConflict
from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)

router = APIRouter(tags=["Knowledge Bases"])
ProductDependencies = Annotated[
    ProductServiceDependencies,
    Depends(get_product_service_dependencies),
]


@router.put(
    "/knowledge-bases/providers/{provider_id}/definitions/{definition_id}",
    response_model=KnowledgeBasePublicationResult,
    summary="Publish a Knowledge Base declaration from its own image.",
)
async def put_knowledge_base_definition(
    provider_id: Annotated[str, Path(min_length=1, pattern=KNOWLEDGE_BASE_ID_PATTERN)],
    definition_id: Annotated[str, Path(min_length=1)],
    body: KnowledgeBasePublicationRequest,
    deps: ProductDependencies,
    # Not `get_current_user`: that dependency enforces persisted GCU acceptance,
    # which is a human admission control. The publisher is a confidential client
    # with no user row and nobody to accept anything — it would always be 403.
    user: KeycloakUser = Depends(get_current_user_without_gcu),
) -> KnowledgeBasePublicationResult:
    """Idempotent upsert, so every deployment of the image replays it.

    The provider is a path segment rather than a body field: it is the
    namespace the calling client is bound to, and it belongs to the address of
    what is being written, not to its content.
    """
    try:
        declaration = KnowledgeBaseDeclaration(
            id=definition_id,
            version=body.version,
            name=body.name,
            description=body.description,
            configuration_fields=body.configuration_fields,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return await knowledge_base_service.publish_definition(
            user=user, provider_id=provider_id, declaration=declaration, deps=deps
        )
    except (
        KnowledgeBaseClientMismatch,
        KnowledgeBaseProviderConflict,
        AuthorizationError,
    ) as exc:
        raise _map_error(exc) from exc
