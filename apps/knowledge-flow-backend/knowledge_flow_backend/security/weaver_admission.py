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

from fastapi import Depends, HTTPException, status
from fred_core.documents.access import SpacePendingDeletionError
from fred_core.security import oidc
from fred_core.security.delegation import AssertedUser
from fred_core.security.structure import KeycloakUser


async def delegated_person(
    subject: KeycloakUser | AssertedUser = Depends(oidc.authenticate_request),
) -> AssertedUser:
    """Accept a verified workload assertion; the pod owns turn admission/lifetime.

    Neither a direct person nor a workload without delegation may supply scope.
    """
    if not isinstance(subject, AssertedUser):
        raise HTTPException(status_code=403, detail="delegated_call_required")
    return subject


def _space_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SpacePendingDeletionError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="space_pending_deletion")
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="space_not_found")
