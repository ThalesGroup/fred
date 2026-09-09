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

"""Shared organization-scoped gates.

Extracted from `capabilities/service.py`'s private `_require_manage_any`
(CAPAB-01 / #1980) now that `routing_policy/service.py`'s platform
model-binding admin surface needs the identical check — both packages import
this instead of one reaching into the other's `_`-prefixed helper.

One helper per organization capability, all through `_require`: the narrow
relations carved out of the `can_manage_platform` catch-all exist precisely so
a delegated surface does NOT reuse the catch-all gate, so they must not share
a parameterised entry point callers could point anywhere.
"""

from __future__ import annotations

from fred_core import KeycloakUser, OrganizationPermission
from fred_core.security.rebac.rebac_engine import ORGANIZATION_ID, RebacEngine


async def _require(
    rebac: RebacEngine, user: KeycloakUser, permission: OrganizationPermission
) -> None:
    await rebac.check_user_permission_or_raise(user, permission, ORGANIZATION_ID)


async def require_manage_any(rebac: RebacEngine, user: KeycloakUser) -> None:
    """Org-admin gate: `OrganizationPermission.CAN_MANAGE_PLATFORM` on the
    organization singleton — the catch-all that also carries import/export,
    tasks and platform reset."""

    await _require(rebac, user, OrganizationPermission.CAN_MANAGE_PLATFORM)


async def require_edit_platform_prompt(rebac: RebacEngine, user: KeycloakUser) -> None:
    """Platform-prompt gate: `can_edit_platform_prompt`, which the schema
    defines as `platform_admin or prompt_editor`. Deliberately NOT
    `can_manage_platform` — that catch-all also carries import/export, tasks
    and platform reset, so editing one prompt could not be delegated through
    it."""

    await _require(rebac, user, OrganizationPermission.CAN_EDIT_PLATFORM_PROMPT)
