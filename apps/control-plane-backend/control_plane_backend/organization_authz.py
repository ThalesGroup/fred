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

One named helper per capability, never a parameterised entry point: the narrow
relations carved out of `can_manage_platform` exist so a delegated surface
cannot reuse the catch-all gate. The catch-all keeps no helper here.
"""

from __future__ import annotations

from fred_core import KeycloakUser, OrganizationPermission
from fred_core.security.rebac.rebac_engine import ORGANIZATION_ID, RebacEngine


async def _require(
    rebac: RebacEngine, user: KeycloakUser, permission: OrganizationPermission
) -> None:
    await rebac.check_user_permission_or_raise(user, permission, ORGANIZATION_ID)


async def require_manage_capabilities(rebac: RebacEngine, user: KeycloakUser) -> None:
    """Feature-governance gate: `can_manage_capabilities`, which the schema
    defines as `platform_admin or feature_manager`. The org-level twin of
    `capability#can_manage`, which resolves through the very same relation."""

    await _require(rebac, user, OrganizationPermission.CAN_MANAGE_CAPABILITIES)


async def require_edit_platform_prompt(rebac: RebacEngine, user: KeycloakUser) -> None:
    """Platform-prompt gate: `can_edit_platform_prompt` (`platform_admin or
    prompt_editor`). Not `can_manage_platform` — that catch-all also carries
    import/export, tasks and platform reset."""

    await _require(rebac, user, OrganizationPermission.CAN_EDIT_PLATFORM_PROMPT)
