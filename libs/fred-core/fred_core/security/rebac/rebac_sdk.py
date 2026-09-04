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

"""Named, fail-closed ReBAC checks for first-party application backends."""

from types import TracebackType as _TracebackType
from typing import Protocol as _Protocol
from typing import cast as _cast

from fred_core.common.team_id import is_personal_team_ref as _is_personal_team_ref
from fred_core.kpi.base_kpi_writer import BaseKPIWriter as _BaseKPIWriter
from fred_core.security.models import AuthorizationError as _AuthorizationError
from fred_core.security.models import Resource as _Resource
from fred_core.security.oidc import apply_security_profile as _apply_security_profile
from fred_core.security.oidc import (
    initialize_user_security as _initialize_user_security,
)
from fred_core.security.rebac.capability_authz import (
    application_capability_id as _application_capability_id,
)
from fred_core.security.rebac.capability_authz import (
    team_capability_subject_and_context as _team_capability_subject_and_context,
)
from fred_core.security.rebac.rebac_engine import (
    CapabilityPermission as _CapabilityPermission,
)
from fred_core.security.rebac.rebac_engine import RebacEngine as _RebacEngine
from fred_core.security.rebac.rebac_engine import RebacReference as _RebacReference
from fred_core.security.rebac.rebac_engine import TeamPermission as _TeamPermission
from fred_core.security.rebac.rebac_factory import rebac_factory as _rebac_factory
from fred_core.security.structure import KeycloakUser as _KeycloakUser
from fred_core.security.structure import OpenFgaRebacConfig as _OpenFgaRebacConfig
from fred_core.security.structure import SecurityConfiguration as _SecurityConfiguration

__all__ = ["RebacSdk", "rebac_sdk_factory"]


class RebacSdk(_Protocol):
    """The complete authorization surface exposed to a first-party backend."""

    async def check_user_team_permission(
        self,
        user: _KeycloakUser,
        permission: _TeamPermission,
        team_id: str,
    ) -> None:
        """Raise unless ``user`` holds ``permission`` on a collaborative team."""
        ...

    async def check_team_capability(
        self,
        team_id: str,
        capability_id: str,
    ) -> None:
        """Raise unless a collaborative ``team_id`` may use ``capability_id``."""
        ...

    async def check_application_access(
        self,
        user: _KeycloakUser,
        *,
        team_id: str,
        app_id: str,
    ) -> None:
        """Raise unless ``user`` may use ``app_id`` in ``team_id``."""
        ...

    async def close(self) -> None:
        """Release the process-scoped OpenFGA client."""
        ...

    async def __aenter__(self) -> "RebacSdk":
        """Return this SDK for process-lifetime async context management."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: _TracebackType | None,
    ) -> None:
        """Release the process-scoped OpenFGA client."""
        ...


class _InitializableRebacEngine(_Protocol):
    async def get_client(self) -> object:
        """Resolve the configured store and cache the process client."""
        ...


class _RebacSdk:
    """Private engine-backed implementation of the named SDK surface."""

    __slots__ = ("__engine",)

    def __init__(self, engine: _RebacEngine) -> None:
        if not engine.enabled:
            raise ValueError(
                "The first-party ReBAC SDK requires an enabled OpenFGA engine"
            )
        self.__engine = engine

    async def check_user_team_permission(
        self,
        user: _KeycloakUser,
        permission: _TeamPermission,
        team_id: str,
    ) -> None:
        if _is_personal_team_ref(team_id):
            raise _AuthorizationError(
                user.uid,
                permission.value,
                _Resource.TEAM,
                f"Team {team_id!r} is a personal space and is outside the application trust tier",
                actor_uid=user.uid,
                subject_type=_Resource.USER,
                subject_id=user.uid,
            )
        await self.__engine.check_user_team_permission_or_raise(
            user, permission, team_id
        )

    async def check_team_capability(
        self,
        team_id: str,
        capability_id: str,
    ) -> None:
        if _is_personal_team_ref(team_id):
            raise _AuthorizationError(
                team_id,
                _CapabilityPermission.CAN_USE.value,
                _Resource.CAPABILITY,
                f"Team {team_id!r} is a personal space and is outside the application trust tier",
                subject_type=_Resource.TEAM,
                subject_id=team_id,
            )
        await self._check_team_capability(team_id, capability_id)

    async def _check_team_capability(
        self,
        team_id: str,
        capability_id: str,
        *,
        user: _KeycloakUser | None = None,
    ) -> None:
        team_ref, context = _team_capability_subject_and_context(team_id)
        await self.__engine.check_permission_or_raise(
            team_ref,
            _CapabilityPermission.CAN_USE,
            _RebacReference(type=_Resource.CAPABILITY, id=capability_id),
            contextual_relations=context,
            actor_uid=user.uid if user else None,
        )

    async def check_application_access(
        self,
        user: _KeycloakUser,
        *,
        team_id: str,
        app_id: str,
    ) -> None:
        if _is_personal_team_ref(team_id):
            raise _AuthorizationError(
                user.uid,
                _TeamPermission.CAN_USE_TEAM_APPLICATIONS.value,
                _Resource.TEAM,
                f"Team {team_id!r} is a personal space and holds no application grants",
                actor_uid=user.uid,
            )

        await self.check_user_team_permission(
            user, _TeamPermission.CAN_USE_TEAM_APPLICATIONS, team_id
        )
        await self._check_team_capability(
            team_id,
            _application_capability_id(app_id),
            user=user,
        )

    async def close(self) -> None:
        await self.__engine.close()

    async def __aenter__(self) -> RebacSdk:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: _TracebackType | None,
    ) -> None:
        await self.close()


async def rebac_sdk_factory(
    security_config: _SecurityConfiguration,
    *,
    kpi_writer: _BaseKPIWriter,
) -> RebacSdk:
    """Build and initialize the process-scoped, fail-closed ReBAC SDK.

    First-party application backends are ReBAC readers, never schema or store
    owners. They must use the hardened C3 profile and supply their process KPI
    writer so every OpenFGA call remains observable.
    """

    writer = _require_kpi_writer(kpi_writer)
    if security_config.profile != "c3":
        raise ValueError("The first-party ReBAC SDK requires security.profile='c3'")

    _apply_security_profile(security_config)
    rebac_config = security_config.rebac
    if not isinstance(rebac_config, _OpenFgaRebacConfig):
        raise ValueError("The first-party ReBAC SDK requires enabled OpenFGA")
    if rebac_config.create_store_if_needed:
        raise ValueError(
            "First-party ReBAC backends must set create_store_if_needed=false"
        )
    if rebac_config.sync_schema_on_init:
        raise ValueError(
            "First-party ReBAC backends must set sync_schema_on_init=false"
        )
    timeout = rebac_config.timeout_millisec
    if timeout is None or not 1 <= timeout <= 30_000:
        raise ValueError(
            "First-party ReBAC backends must set timeout_millisec between 1 and 30000"
        )
    if not security_config.user.client_id.strip():
        raise ValueError(
            "First-party ReBAC backends must set security.user.client_id to the exact "
            "JWT audience; configure a Keycloak audience mapper instead of leaving it blank"
        )

    _initialize_user_security(security_config.user)
    engine = _rebac_factory(security_config, kpi_writer=writer)
    sdk = _RebacSdk(engine)
    await _cast(_InitializableRebacEngine, engine).get_client()
    return sdk


def _require_kpi_writer(
    kpi_writer: _BaseKPIWriter | None,
) -> _BaseKPIWriter:
    if kpi_writer is None:
        raise ValueError("The first-party ReBAC SDK requires a process KPI writer")
    return kpi_writer
