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

"""Tests for the C3 security profile (RUNTIME-07 rev. 2, F5/F6).

The C3 profile forces strict JWT issuer/audience validation, forbids
no-security/mock-admin, and requires OpenFGA ReBAC to be enabled so the pod
authorizes every request and fails closed. There is no signed grant.
"""

from typing import Literal

import pytest
from pydantic import AnyHttpUrl, AnyUrl

from fred_core.security import oidc
from fred_core.security.structure import (
    M2MSecurity,
    OpenFgaRebacConfig,
    SecurityConfiguration,
    UserSecurity,
)

_REALM = AnyUrl("http://localhost:8080/realms/app")


def _security(
    *,
    profile: Literal["c3"] | None = None,
    user: bool = True,
    m2m: bool = True,
    rebac: bool = True,
):
    rebac_cfg = (
        OpenFgaRebacConfig(enabled=rebac, api_url=AnyHttpUrl("http://fga:8080"))
        if rebac
        else None
    )
    return SecurityConfiguration(
        m2m=M2MSecurity(enabled=m2m, realm_url=_REALM, client_id="cp"),
        user=UserSecurity(enabled=user, realm_url=_REALM, client_id="app"),
        rebac=rebac_cfg,
        profile=profile,
    )


@pytest.fixture(autouse=True)
def _restore_strict_flags():
    before = (oidc.STRICT_ISSUER, oidc.STRICT_AUDIENCE)
    yield
    oidc.STRICT_ISSUER, oidc.STRICT_AUDIENCE = before


def test_non_c3_profile_is_noop() -> None:
    oidc.STRICT_ISSUER = False
    oidc.STRICT_AUDIENCE = False
    oidc.apply_security_profile(_security(profile=None, user=False, rebac=False))
    # No exception, and strict flags untouched.
    assert oidc.STRICT_ISSUER is False
    assert oidc.STRICT_AUDIENCE is False


def test_c3_profile_forces_strict_jwt() -> None:
    oidc.STRICT_ISSUER = False
    oidc.STRICT_AUDIENCE = False
    oidc.apply_security_profile(_security(profile="c3"))
    assert oidc.STRICT_ISSUER is True
    assert oidc.STRICT_AUDIENCE is True


def test_c3_rejects_no_security() -> None:
    with pytest.raises(ValueError, match="user.enabled must be true"):
        oidc.apply_security_profile(_security(profile="c3", user=False))


def test_c3_requires_m2m() -> None:
    with pytest.raises(ValueError, match="m2m.enabled must be true"):
        oidc.apply_security_profile(_security(profile="c3", m2m=False))


def test_c3_requires_rebac_enabled() -> None:
    with pytest.raises(ValueError, match="rebac.enabled must be true"):
        oidc.apply_security_profile(_security(profile="c3", rebac=False))


def test_c3_happy_path_does_not_raise() -> None:
    oidc.apply_security_profile(_security(profile="c3"))  # no exception
