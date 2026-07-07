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

import httpx
from fred_core.cli.auth import (
    KeycloakLoginConfig,
    KeycloakUserSessionManager,
    build_cli_token_provider,
    resolve_keycloak_login_config,
)


def test_resolve_keycloak_login_config_reads_backend_configuration(tmp_path) -> None:
    """
    Verify shared CLI auth discovery reads `security.user` from config.

    Why this test exists:
    - multiple Fred CLIs should discover Keycloak settings from the backend
      configuration file instead of retyping them

    How to use it:
    - run with the default offline `fred-core` test suite

    Example:
    - `pytest fred_core/tests/cli/test_auth.py -q`
    """

    config_file = tmp_path / "configuration.yaml"
    config_file.write_text(
        """
security:
  user:
    enabled: true
    realm_url: "http://localhost:8080/realms/app"
    client_id: "app"
""".strip(),
        encoding="utf-8",
    )
    ignored_secret_env_var_name = "_".join(["IGNORED", "SECRET"])

    config = resolve_keycloak_login_config(
        realm_url=None,
        client_id=None,
        client_secret=None,
        config_file=config_file,
        realm_env_var="IGNORED_REALM",
        client_id_env_var="IGNORED_CLIENT",
        client_secret_env_var=ignored_secret_env_var_name,
    )

    assert config is not None
    assert config.realm_url == "http://localhost:8080/realms/app"
    assert config.client_id == "app"


def test_build_cli_token_provider_falls_back_after_refresh_failure(
    tmp_path, capsys
) -> None:
    """
    Verify the shared token provider does not block CLI startup on bad refresh.

    Why this test exists:
    - all Fred CLIs should remain usable when a cached refresh token is revoked
      or expired

    How to use it:
    - run with the default offline `fred-core` test suite

    Example:
    - `pytest fred_core/tests/cli/test_auth.py -q`
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    auth_http = httpx.Client(transport=httpx.MockTransport(handler), timeout=10.0)
    manager = KeycloakUserSessionManager(
        config=KeycloakLoginConfig(
            realm_url="http://localhost:8080/realms/app",
            client_id="app",
        ),
        cache_file=tmp_path / "session.json",
        log_prefix="[test-cli]",
        http_client=auth_http,
    )
    expired_access_value = "-".join(["expired", "access"])
    expired_refresh_value = "-".join(["expired", "refresh"])
    manager._session = manager._build_session_from_token_payload(
        {
            "access_token": expired_access_value,
            "refresh_token": expired_refresh_value,
            "expires_in": 0,
        },
        username="alice",
    )
    manager._session.expires_at_timestamp = 0

    token_provider = build_cli_token_provider(
        auth_session=manager,
        static_token=None,
        log_prefix="[test-cli]",
    )

    assert token_provider() is None
    assert manager.is_logged_in() is False
    assert "Use /login to authenticate again." in capsys.readouterr().out

    manager.close()
    auth_http.close()
