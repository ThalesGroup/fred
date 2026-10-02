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
from __future__ import annotations

from fred_core import KeycloakUser, OrganizationPermission
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.rebac.rebac_engine import ORGANIZATION_ID

from control_plane_backend.platform_ui_settings.schemas import (
    PlatformUiSettings,
    SetPlatformUiSettingsRequest,
)
from control_plane_backend.platform_ui_settings.store import StoredPlatformUiSettings
from control_plane_backend.product.dependencies import ProductServiceDependencies


async def _require_manage_platform(
    deps: ProductServiceDependencies, user: KeycloakUser
) -> None:
    # Same catch-all platform gate as announcements: a platform-wide presentation setting.
    await deps.team_dependencies.rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
    )


def _to_settings(stored: StoredPlatformUiSettings | None) -> PlatformUiSettings:
    if stored is None:
        return PlatformUiSettings()
    return PlatformUiSettings(
        default_theme=stored.default_theme,
        hidden_themes=stored.hidden_themes,
        updated_by=stored.updated_by,
        updated_at=stored.updated_at,
    )


async def get_platform_ui_settings(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> PlatformUiSettings:
    await _require_manage_platform(deps, user)
    return _to_settings(await deps.get_platform_ui_settings_store().get())


async def set_platform_ui_settings(
    *,
    user: KeycloakUser,
    request: SetPlatformUiSettingsRequest,
    deps: ProductServiceDependencies,
) -> PlatformUiSettings:
    await _require_manage_platform(deps, user)
    stored = await deps.get_platform_ui_settings_store().set(
        default_theme=request.default_theme,
        hidden_themes=request.hidden_themes,
        updated_by=user.uid,
    )
    emit_audit_log(
        "platform.ui_settings.updated",
        actor_uid=user.uid,
        default_theme=request.default_theme,
        hidden_themes=request.hidden_themes,
    )
    return _to_settings(stored)
