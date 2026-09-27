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
from unittest.mock import AsyncMock

import pytest

from control_plane_backend.teams import service


@pytest.mark.asyncio
async def test_local_personal_space_count_uses_store(monkeypatch):
    store = SimpleNamespace(count_identities=AsyncMock(return_value=7))
    monkeypatch.setattr(service, "get_user_store", lambda: store)
    monkeypatch.setattr(
        service,
        "create_keycloak_admin",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Keycloak Admin API must not be constructed")
        ),
    )
    deps = SimpleNamespace(
        configuration=SimpleNamespace(security=SimpleNamespace(user_directory="local"))
    )

    assert await service.count_all_personal_spaces(deps) == 7
