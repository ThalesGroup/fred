# Copyright Thales 2025
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

from uuid import UUID

import pytest

from fred_core.security import oidc


def test_decode_jwt_offline_returns_uuid_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", False)

    user = oidc.decode_jwt("ignored")
    assert UUID(user.uid)


@pytest.mark.asyncio
async def test_get_current_user_without_gcu_offline_returns_uuid_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", False)

    user = await oidc.get_current_user_without_gcu(token="ignored")  # nosec B106
    assert UUID(user.uid)
