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

"""Who may call Knowledge Flow API, and for which space."""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from fred_core.documents.access import SpacePendingDeletionError
from fred_core.security import oidc
from fred_core.security.control_plane import authorization_request
from fred_core.security.delegation import AssertedUser
from fred_core.security.structure import KeycloakUser
from pydantic import BaseModel, ConfigDict

from knowledge_flow_backend.application_context import get_app_context


async def delegated_person(
    subject: KeycloakUser | AssertedUser = Depends(oidc.authenticate_request),
) -> AssertedUser:
    """Only an agent pod acting for a person, inside a turn Control Plane admitted.

    A direct person or service token is refused, so no call bypasses that admission.
    """
    if not isinstance(subject, AssertedUser):
        raise HTTPException(status_code=403, detail="delegated_call_required")
    return subject


class AuthorizedScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    space_id: UUID
    space_ids: tuple[UUID, ...]


async def require_space_read(person: AssertedUser, space_id: UUID) -> tuple[UUID, ...]:
    """One fresh scope decision, using this service's credential and verified person."""
    context = get_app_context()
    url = context.configuration.control_plane_url
    if not url:
        raise HTTPException(503, "authorization_unavailable")
    try:
        result = await authorization_request(
            context.get_authorization_client(),
            f"{url.rstrip('/')}/authorize/scope",
            {"space_id": str(space_id)},
            params={"person": person.uid, "run": person.run_id, "agent": person.agent_id},
        )
        scope = AuthorizedScope.model_validate(result)
        if scope.space_id != space_id or len(set(scope.space_ids)) != len(scope.space_ids):
            raise ValueError("Invalid scope anchor or duplicates")
        return scope.space_ids
    except HTTPException as exc:
        if exc.status_code == 401:
            raise HTTPException(503, "authorization_unavailable") from None
        raise
    except (ValueError, RuntimeError):
        raise HTTPException(503, "authorization_unavailable") from None


def _space_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SpacePendingDeletionError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="space_pending_deletion")
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="space_not_found")
