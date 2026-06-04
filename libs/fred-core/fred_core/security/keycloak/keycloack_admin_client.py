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

import logging
import os

from keycloak import KeycloakAdmin

from fred_core.security.oidc import split_realm_url
from fred_core.security.structure import M2MSecurity

logger = logging.getLogger(__name__)


class KeycloackDisabled:
    """
    Class used to represent Keycloack clien createtion result when it is disabled,
    to let know the caller it must handle this case.
    """

    ...


def create_keycloak_admin(
    m2m_security: M2MSecurity,
) -> KeycloakAdmin | KeycloackDisabled:
    """Create a Keycloak admin client using the configured service account. Returns KeycloackDisabled if M2M security is not enabled."""

    if not m2m_security or not m2m_security.enabled:
        return KeycloackDisabled()

    client_secret = os.getenv(m2m_security.secret_env_var)
    if not client_secret:
        raise RuntimeError(
            f"{m2m_security.secret_env_var} is not set; cannot create Keycloak admin client."
        )

    try:
        server_url, realm = split_realm_url(str(m2m_security.realm_url))
    except ValueError as exc:
        raise RuntimeError(
            "Invalid Keycloak realm URL configured; cannot create Keycloak admin client."
        ) from exc

    return KeycloakAdmin(
        server_url=_ensure_trailing_slash(server_url),
        realm_name=realm,
        client_id=m2m_security.client_id,
        client_secret_key=client_secret,
        user_realm_name=realm,
    )


def _ensure_trailing_slash(url: str) -> str:
    return url if url.endswith("/") else f"{url}/"
