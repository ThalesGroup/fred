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

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.service import build_frontend_config
from fred_pod.security.structure import PlatformAccessConfiguration
from pydantic import AnyHttpUrl


@pytest.mark.asyncio
async def test_frontend_config_exposes_public_oidc_settings() -> None:
    user = SimpleNamespace(
        enabled=True,
        realm_url="https://identity.example/tenant/v2.0",
        client_id="ui-client",
        provider="oidc",
        scope="api://fred/access_as_user",
        claims=SimpleNamespace(uid="oid"),
        roles_claim=["roles"],
    )
    configuration = SimpleNamespace(
        security=SimpleNamespace(
            user=user,
            user_directory="local",
            platform_access=PlatformAccessConfiguration(),
        ),
        app=SimpleNamespace(gcu_version=None),
        platform=SimpleNamespace(frontend=SimpleNamespace(info_banner=None)),
    )
    deps = SimpleNamespace(
        configuration=configuration,
        get_platform_bootstrap_store=lambda: SimpleNamespace(
            is_completed=AsyncMock(return_value=False)
        ),
        team_dependencies=SimpleNamespace(rebac=SimpleNamespace(enabled=True)),
    )

    payload = await build_frontend_config(cast(ProductServiceDependencies, deps))

    assert payload.platform_access_enabled is False
    assert payload.supportLink is None

    assert payload.user_auth.model_dump() == {
        "enabled": True,
        "realm_url": "https://identity.example/tenant/v2.0",
        "client_id": "ui-client",
        "provider": "oidc",
        "scope": "api://fred/access_as_user",
        "user_directory": "local",
        "uid_claim": "oid",
        "roles_claim": ["roles"],
    }

    configuration.security.platform_access = PlatformAccessConfiguration(
        enabled=True,
        jwt_claim=["profile", "unit"],
        accepted_regex="accepted",
        supportLink=AnyHttpUrl("https://support.example.org"),
    )
    configured = await build_frontend_config(cast(ProductServiceDependencies, deps))
    assert configured.platform_access_enabled is True
    assert configured.supportLink == "https://support.example.org/"
