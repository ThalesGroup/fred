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

from fastapi import Depends, HTTPException
from fred_core.security import oidc
from fred_core.security.delegation import AssertedUser
from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import RebacReference, SpacePermission
from fred_core.security.structure import KeycloakUser

from knowledge_flow_backend.application_context import get_rebac_engine


async def delegated_person(
    subject: KeycloakUser | AssertedUser = Depends(oidc.authenticate_request),
) -> AssertedUser:
    """Only an agent pod acting for a person, inside a turn Control Plane admitted.

    A direct person or service token is refused, so no call bypasses that admission.
    """
    if not isinstance(subject, AssertedUser):
        raise HTTPException(status_code=403, detail="delegated_call_required")
    return subject


async def require_space_read(person: AssertedUser, space_id: UUID) -> None:
    """One check on the published Weaver model; documents derive from their space."""
    await get_rebac_engine().check_permission_or_raise(
        RebacReference(Resource.USER, person.uid),
        SpacePermission.CAN_READ,
        RebacReference(Resource.SPACE, str(space_id)),
    )
