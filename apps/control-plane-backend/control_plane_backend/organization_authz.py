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

"""Shared org-admin gate.

Extracted from `capabilities/service.py`'s private `_require_manage_any`
(CAPAB-01 / #1980) now that `routing_policy/service.py`'s platform
model-binding admin surface needs the identical check — both packages import
this instead of one reaching into the other's `_`-prefixed helper.
"""

from __future__ import annotations

from fred_core import KeycloakUser, OrganizationPermission
from fred_core.security.rebac.rebac_engine import ORGANIZATION_ID, RebacEngine


async def require_manage_any(rebac: RebacEngine, user: KeycloakUser) -> None:
    """Org-admin gate: `OrganizationPermission.CAN_MANAGE_PLATFORM` on the
    organization singleton — the same relation `capability#can_manage`
    ultimately resolves to for the aggregate capability list."""

    await rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
    )
