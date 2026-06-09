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

import base64
import hashlib
import json
import logging
import os
import secrets
import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from fred_core.common import ConfigFiles, parse_yaml_mapping_file

logger = logging.getLogger(__name__)

DEFAULT_PKCE_CALLBACK_HOST = "127.0.0.1"
DEFAULT_PKCE_CALLBACK_PORT = 8765
DEFAULT_KEYCLOAK_TOKEN_FILE = (  # nosec B105 - local cache path, not a credential
    "~/.config/fred/agent-chat-session.json"
)


@dataclass(slots=True)
class KeycloakPkceLoginRequest:
    """
    One prepared Keycloak PKCE authorization request for a CLI login flow.

    Why this class exists:
    - browser login needs several tightly coupled values that must stay aligned:
      auth URL, redirect URI, state, and PKCE verifier
    - keeping them together makes browser login easier to test and reuse

    How to use it:
    - build it with `KeycloakUserSessionManager.build_pkce_login_request(...)`
    - pass it to `login_with_pkce(...)` or inspect the authorization URL

    Example:
    - `request = auth.build_pkce_login_request(callback_host="127.0.0.1", callback_port=8765)`
    """

    authorization_url: str
    redirect_uri: str
    state: str
    code_verifier: str


@dataclass(slots=True)
class KeycloakLoginConfig:
    """
    Minimal Keycloak settings required for CLI user login.

    Why this class exists:
    - Fred CLIs should authenticate real users without depending on the
      frontend UI
    - grouping the coordinates keeps login, refresh, and cache handling typed
      and explicit

    How to use it:
    - build it from CLI flags, env vars, or one backend configuration file
    - pass it to `KeycloakUserSessionManager`

    Example:
    - `cfg = KeycloakLoginConfig(realm_url="http://localhost:8080/realms/app", client_id="app")`
    """

    realm_url: str
    client_id: str
    client_secret: str | None = None


@dataclass(slots=True)
class KeycloakUserSession:
    """
    Serializable CLI user session cached on disk.

    Why this class exists:
    - secured manual testing should survive CLI restarts without forcing a
      fresh login every time
    - access/refresh token lifecycle belongs to the CLI session state, not to
      backend-specific HTTP clients

    How to use it:
    - created by `KeycloakUserSessionManager.login(...)`
    - persisted to disk and refreshed automatically when needed

    Example:
    - `session = KeycloakUserSession(username="alice", access_token="...", refresh_token="...", expires_at_timestamp=123.0, realm_url="...", client_id="...")`
    """

    username: str
    access_token: str
    refresh_token: str | None
    expires_at_timestamp: float
    realm_url: str
    client_id: str

    def to_payload(self) -> dict[str, Any]:
        """
        Convert the session into a JSON-serializable payload.

        Why this function exists:
        - the CLI cache file stores one tiny JSON object on disk

        How to use it:
        - call before writing the session to the local cache file

        Example:
        - `payload = session.to_payload()`
        """

        return {
            "username": self.username,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at_timestamp": self.expires_at_timestamp,
            "realm_url": self.realm_url,
            "client_id": self.client_id,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "KeycloakUserSession":
        """
        Restore one cached session from a decoded JSON payload.

        Why this function exists:
        - CLI login state must be rehydrated when the process starts

        How to use it:
        - pass the JSON object loaded from the cache file

        Example:
        - `session = KeycloakUserSession.from_payload(raw_payload)`
        """

        return cls(
            username=str(payload["username"]),
            access_token=str(payload["access_token"]),
            refresh_token=(
                str(payload["refresh_token"])
                if payload.get("refresh_token") is not None
                else None
            ),
            expires_at_timestamp=float(payload["expires_at_timestamp"]),
            realm_url=str(payload["realm_url"]),
            client_id=str(payload["client_id"]),
        )


class KeycloakUserSessionManager:
    """
    Manage Keycloak login, refresh, and local token caching for one CLI.

    Why this class exists:
    - Fred needs production-like CLI login support without frontend
      dependencies
    - multiple CLIs should share one robust session/cache implementation

    How to use it:
    - instantiate it with resolved Keycloak settings and a cache file path
    - call `login(...)` or `login_with_pkce(...)`
    - pass `get_access_token` into the backend-specific HTTP client

    Example:
    - `auth = KeycloakUserSessionManager(config=cfg, cache_file=Path("~/.config/fred/agent-chat-session.json").expanduser(), log_prefix="[chat]")`
    """

    def __init__(
        self,
        *,
        config: KeycloakLoginConfig,
        cache_file: Path,
        log_prefix: str = "[cli]",
        http_client: httpx.Client | None = None,
    ) -> None:
        self._config = config
        self._cache_file = cache_file
        self._log_prefix = log_prefix
        self._http_client = http_client or httpx.Client(timeout=10.0)
        self._owns_http_client = http_client is None
        self._session: KeycloakUserSession | None = self._load_cached_session()

    def close(self) -> None:
        """
        Close the internal HTTP client when this manager owns it.

        Why this function exists:
        - the login manager may create its own `httpx.Client` for token calls
        - CLI shutdown should release those resources cleanly

        How to use it:
        - call from the CLI `finally:` block

        Example:
        - `auth.close()`
        """

        if self._owns_http_client:
            self._http_client.close()

    def is_logged_in(self) -> bool:
        """
        Tell whether the CLI currently has a cached user session.

        Why this function exists:
        - interactive consoles need a quick auth-state check for `/whoami`,
          `/logout`, and startup banners

        How to use it:
        - call before rendering auth-sensitive commands

        Example:
        - `if auth.is_logged_in(): ...`
        """

        return self._session is not None

    def current_username(self) -> str | None:
        """
        Return the logged-in username when one cached session exists.

        Why this function exists:
        - REPLs should expose the active user identity without inspecting raw
          token payloads

        How to use it:
        - call after login or from `/whoami`

        Example:
        - `username = auth.current_username()`
        """

        return self._session.username if self._session is not None else None

    def describe(self) -> str:
        """
        Return a short human-readable description of the auth state.

        Why this function exists:
        - Fred CLIs should expose auth state without printing raw token data

        How to use it:
        - show it in a REPL banner or `whoami` command

        Example:
        - `print(auth.describe())`
        """

        if self._session is None:
            return "not logged in"
        expires = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(self._session.expires_at_timestamp)
        )
        return (
            f"{self._session.username} "
            f"(client={self._session.client_id}, expires={expires})"
        )

    def login(self, *, username: str, password: str) -> None:
        """
        Authenticate one user with the Keycloak password grant.

        Why this function exists:
        - local and production-like CLI workflows still need a frontend-free
          fallback login mode

        How to use it:
        - call with a prompted username/password pair
        - the resulting session is cached automatically

        """

        form = {
            "grant_type": "password",
            "client_id": self._config.client_id,
            "username": username,
            "password": password,
        }
        if self._config.client_secret:
            form["client_secret"] = self._config.client_secret

        print(
            f"{self._log_prefix} connecting to keycloak: POST {self._token_url()} (password grant)"
        )
        response = self._http_client.post(self._token_url(), data=form)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Keycloak token response must be a JSON object.")
        self._session = self._build_session_from_token_payload(
            payload,
            username=username,
        )
        self._save_cached_session()

    def build_pkce_login_request(
        self,
        *,
        callback_host: str = DEFAULT_PKCE_CALLBACK_HOST,
        callback_port: int = DEFAULT_PKCE_CALLBACK_PORT,
    ) -> KeycloakPkceLoginRequest:
        """
        Prepare one browser-based PKCE authorization request.

        Why this function exists:
        - browser login should be reusable across Fred CLIs, not reimplemented
          per backend

        How to use it:
        - call before starting one PKCE login flow
        - ensure Keycloak allows the returned redirect URI

        Example:
        - `request = auth.build_pkce_login_request(callback_host="127.0.0.1", callback_port=8765)`
        """

        redirect_uri = f"http://{callback_host}:{callback_port}/callback"
        state = secrets.token_urlsafe(24)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = self._pkce_code_challenge(code_verifier)
        params = {
            "client_id": self._config.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid profile email",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return KeycloakPkceLoginRequest(
            authorization_url=f"{self._authorization_url()}?{urlencode(params)}",
            redirect_uri=redirect_uri,
            state=state,
            code_verifier=code_verifier,
        )

    def login_with_pkce(
        self,
        *,
        callback_host: str = DEFAULT_PKCE_CALLBACK_HOST,
        callback_port: int = DEFAULT_PKCE_CALLBACK_PORT,
        timeout_seconds: int = 300,
        url_opener: Callable[[str], bool] | None = None,
    ) -> None:
        """
        Authenticate one user through Keycloak's PKCE browser flow.

        Why this function exists:
        - production-like CLI usage should mirror the frontend login family when
          possible

        How to use it:
        - ensure the Keycloak client allows the loopback redirect URI
        - call from the CLI and complete login in the browser

        Example:
        - `auth.login_with_pkce(callback_host="127.0.0.1", callback_port=8765)`
        """

        request = self.build_pkce_login_request(
            callback_host=callback_host,
            callback_port=callback_port,
        )
        print(
            "Complete login in your browser. If it does not open automatically, "
            "open this URL:"
        )
        print(request.authorization_url)
        opener = url_opener or webbrowser.open
        try:
            opener(request.authorization_url)
        except Exception:
            logger.exception(
                "%s Failed to open the browser automatically", self._log_prefix
            )
        authorization_code = self._wait_for_pkce_callback(
            request,
            timeout_seconds=timeout_seconds,
        )
        payload = self._exchange_authorization_code(
            authorization_code=authorization_code,
            pkce_request=request,
        )
        self._session = self._build_session_from_token_payload(
            payload,
            username=self._username_from_access_token(payload.get("access_token")),
        )
        self._save_cached_session()

    def logout(self) -> None:
        """
        Clear the cached login session and local token file.

        Why this function exists:
        - CLIs should let developers switch identity or recover from a broken
          cached session explicitly

        How to use it:
        - call from `/logout` or after a failed refresh

        Example:
        - `auth.logout()`
        """

        self._session = None
        if self._cache_file.exists():
            self._cache_file.unlink()

    def get_access_token(self) -> str | None:
        """
        Return one valid access token, refreshing it when needed.

        Why this function exists:
        - backend-specific HTTP clients need a tiny bearer-token provider
        - long manual sessions should survive access-token expiry transparently

        How to use it:
        - pass this method directly as the CLI token provider

        Example:
        - `token = auth.get_access_token()`
        """

        if self._session is None:
            return None
        if time.time() < self._session.expires_at_timestamp - 30:
            return self._session.access_token
        self._refresh_session()
        return self._session.access_token if self._session is not None else None

    def _token_url(self) -> str:
        """Return the token endpoint for the configured Keycloak realm URL."""

        return f"{self._config.realm_url.rstrip('/')}/protocol/openid-connect/token"

    def _authorization_url(self) -> str:
        """
        Return the browser authorization endpoint for the configured realm URL.

        Why this function exists:
        - PKCE login needs the auth endpoint alongside the token endpoint

        How to use it:
        - called internally when building one PKCE request

        Example:
        - `url = self._authorization_url()`
        """

        return f"{self._config.realm_url.rstrip('/')}/protocol/openid-connect/auth"

    def _load_cached_session(self) -> KeycloakUserSession | None:
        """
        Restore a previously saved CLI session from disk.

        Why this function exists:
        - login should persist between CLI runs

        How to use it:
        - called internally during manager construction

        Example:
        - `session = self._load_cached_session()`
        """

        if not self._cache_file.exists():
            return None
        payload = json.loads(self._cache_file.read_text(encoding="utf-8"))
        session = KeycloakUserSession.from_payload(payload)
        if (
            session.realm_url != self._config.realm_url
            or session.client_id != self._config.client_id
        ):
            return None
        return session

    def _save_cached_session(self) -> None:
        """
        Persist the current login session to disk.

        Why this function exists:
        - repeated secured testing should not require logging in on every CLI
          startup

        How to use it:
        - called internally after login and refresh

        Example:
        - `self._save_cached_session()`
        """

        if self._session is None:
            return
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._cache_file.write_text(
            json.dumps(self._session.to_payload(), indent=2),
            encoding="utf-8",
        )

    def _refresh_session(self) -> None:
        """
        Refresh the cached session using the stored refresh token.

        Why this function exists:
        - long-lived CLI sessions should keep working after access-token expiry
          without forcing a fresh login every time

        How to use it:
        - called internally by `get_access_token()` when needed

        Example:
        - `self._refresh_session()`
        """

        if self._session is None or not self._session.refresh_token:
            self.logout()
            raise RuntimeError("No refresh token is available. Please /login again.")

        form = {
            "grant_type": "refresh_token",
            "client_id": self._config.client_id,
            "refresh_token": self._session.refresh_token,
        }
        if self._config.client_secret:
            form["client_secret"] = self._config.client_secret

        try:
            print(
                f"{self._log_prefix} connecting to keycloak: POST {self._token_url()} (refresh grant)"
            )
            response = self._http_client.post(self._token_url(), data=form)
            response.raise_for_status()
        except httpx.HTTPError:
            self.logout()
            raise

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Keycloak refresh response must be a JSON object.")
        self._session = self._build_session_from_token_payload(
            payload,
            username=self._session.username,
            fallback_refresh_token=self._session.refresh_token,
        )
        self._save_cached_session()

    def _wait_for_pkce_callback(
        self,
        request: KeycloakPkceLoginRequest,
        *,
        timeout_seconds: int,
    ) -> str:
        """
        Wait for one loopback-browser callback carrying the auth code.

        Why this function exists:
        - the CLI must receive the browser redirect locally to finish PKCE
          without a dedicated web app

        How to use it:
        - called internally by `login_with_pkce(...)`
        - raises `RuntimeError` on timeout, state mismatch, or callback error

        Example:
        - `code = self._wait_for_pkce_callback(request, timeout_seconds=300)`
        """

        callback = urlparse(request.redirect_uri)
        result: dict[str, str] = {}
        result_ready = threading.Event()
        expected_path = callback.path or "/"

        class _PkceCallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
                parsed = urlparse(self.path)
                if parsed.path != expected_path:
                    self.send_response(404)
                    self.end_headers()
                    return

                params = parse_qs(parsed.query)
                if params.get("state", [""])[0] != request.state:
                    result["error"] = "State mismatch in PKCE callback."
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"PKCE state mismatch. You can close this window.")
                    result_ready.set()
                    return
                if "error" in params:
                    result["error"] = params["error"][0]
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Login failed. You can close this window.")
                    result_ready.set()
                    return
                code = params.get("code", [""])[0]
                if not code:
                    result["error"] = "Missing authorization code in PKCE callback."
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(
                        b"Missing authorization code. You can close this window."
                    )
                    result_ready.set()
                    return

                result["code"] = code
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h1>Login complete</h1>"
                    b"<p>You can close this window and return to the CLI.</p>"
                    b"</body></html>"
                )
                result_ready.set()

            def log_message(
                self,
                format: str,
                *args: Any,  # noqa: A002 - stdlib signature
            ) -> None:
                return

        server = HTTPServer(
            (callback.hostname or "", callback.port or 0), _PkceCallbackHandler
        )
        server.timeout = timeout_seconds
        server_thread = threading.Thread(target=server.handle_request, daemon=True)
        server_thread.start()
        try:
            if not result_ready.wait(timeout_seconds):
                raise RuntimeError(
                    "Timed out waiting for the browser login callback. Please try /login again."
                )
            if "error" in result:
                raise RuntimeError(result["error"])
            code = result.get("code")
            if not code:
                raise RuntimeError("PKCE login did not return an authorization code.")
            return code
        finally:
            server.server_close()
            server_thread.join(timeout=1)

    def _exchange_authorization_code(
        self,
        *,
        authorization_code: str,
        pkce_request: KeycloakPkceLoginRequest,
    ) -> dict[str, Any]:
        """
        Exchange one PKCE authorization code for tokens.

        Why this function exists:
        - browser login still ends with one token exchange at the Keycloak token
          endpoint

        How to use it:
        - called internally by `login_with_pkce(...)`

        Example:
        - `payload = self._exchange_authorization_code(authorization_code=code, pkce_request=request)`
        """

        form = {
            "grant_type": "authorization_code",
            "client_id": self._config.client_id,
            "code": authorization_code,
            "redirect_uri": pkce_request.redirect_uri,
            "code_verifier": pkce_request.code_verifier,
        }
        if self._config.client_secret:
            form["client_secret"] = self._config.client_secret

        print(
            f"{self._log_prefix} connecting to keycloak: POST {self._token_url()} (authorization_code grant)"
        )
        response = self._http_client.post(self._token_url(), data=form)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Keycloak PKCE token response must be a JSON object.")
        return payload

    def _build_session_from_token_payload(
        self,
        payload: dict[str, Any],
        *,
        username: str | None,
        fallback_refresh_token: str | None = None,
    ) -> KeycloakUserSession:
        """
        Convert one Keycloak token payload into the cached session model.

        Why this function exists:
        - password login, PKCE login, and refresh all produce the same payload
          shape and should build sessions consistently

        How to use it:
        - pass the JSON payload returned by Keycloak plus the known username

        Example:
        - `session = self._build_session_from_token_payload(payload, username="alice")`
        """

        resolved_username = username or "unknown-user"
        return KeycloakUserSession(
            username=resolved_username,
            access_token=str(payload["access_token"]),
            refresh_token=(
                str(payload["refresh_token"])
                if payload.get("refresh_token") is not None
                else fallback_refresh_token
            ),
            expires_at_timestamp=self._expires_at_from_payload(payload),
            realm_url=self._config.realm_url,
            client_id=self._config.client_id,
        )

    @staticmethod
    def _expires_at_from_payload(payload: dict[str, Any]) -> float:
        """
        Compute one normalized token-expiry timestamp from a Keycloak payload.

        Why this function exists:
        - all login flows should converge on the same cached expiry field

        How to use it:
        - pass the decoded JSON body returned by Keycloak

        Example:
        - `expires_at = KeycloakUserSessionManager._expires_at_from_payload(payload)`
        """

        expires_in = int(payload.get("expires_in", 60))
        return time.time() + max(0, expires_in - 10)

    @staticmethod
    def _pkce_code_challenge(code_verifier: str) -> str:
        """
        Derive the PKCE S256 code challenge from one verifier string.

        Why this function exists:
        - Keycloak PKCE requires a deterministic challenge derived from the
          generated verifier

        How to use it:
        - pass the verifier used in the browser authorization request

        Example:
        - `challenge = KeycloakUserSessionManager._pkce_code_challenge(verifier)`
        """

        digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

    @staticmethod
    def _username_from_access_token(access_token: Any) -> str | None:
        """
        Extract a friendly username from an access-token JWT payload.

        Why this function exists:
        - PKCE login does not prompt for a username, but the CLI still needs a
          friendly identity label for `/whoami`

        How to use it:
        - pass the raw `access_token` string returned by Keycloak

        Example:
        - `username = KeycloakUserSessionManager._username_from_access_token(token)`
        """

        if not isinstance(access_token, str):
            return None
        parts = access_token.split(".")
        if len(parts) < 2:
            return None
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        try:
            claims = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        except Exception:
            return None
        for key in ("preferred_username", "name", "sub"):
            value = claims.get(key)
            if isinstance(value, str) and value:
                return value
        return None


def default_keycloak_token_file(
    *,
    env_var_name: str = "FRED_AGENT_TOKEN_FILE",
    default_path: str = DEFAULT_KEYCLOAK_TOKEN_FILE,
) -> Path:
    """
    Resolve the local CLI token-cache file path.

    Why this function exists:
    - each CLI needs one predictable token cache while still allowing
      environment-specific overrides

    How to use it:
    - keep the defaults for `fred-agent-chat`
    - override `env_var_name` and `default_path` in other CLIs

    Example:
    - `cache_file = default_keycloak_token_file()`
    """

    return Path(os.getenv(env_var_name, default_path)).expanduser()


def default_pkce_callback_host(
    *,
    env_var_name: str = "FRED_AGENT_KEYCLOAK_CALLBACK_HOST",
    default_host: str = DEFAULT_PKCE_CALLBACK_HOST,
) -> str:
    """
    Return the loopback host used for browser PKCE callbacks.

    Why this function exists:
    - CLIs need one predictable callback host that operators can still override
      without editing code

    How to use it:
    - keep the defaults for `fred-agent-chat`
    - override `env_var_name` when another CLI uses its own env prefix

    Example:
    - `host = default_pkce_callback_host()`
    """

    return os.getenv(env_var_name, default_host)


def default_pkce_callback_port(
    *,
    env_var_name: str = "FRED_AGENT_KEYCLOAK_CALLBACK_PORT",
    default_port: int = DEFAULT_PKCE_CALLBACK_PORT,
) -> int:
    """
    Return the loopback port used for browser PKCE callbacks.

    Why this function exists:
    - PKCE login needs one stable local callback port with an env override for
      local conflicts

    How to use it:
    - keep the defaults for `fred-agent-chat`
    - override `env_var_name` when another CLI uses its own env prefix

    Example:
    - `port = default_pkce_callback_port()`
    """

    return int(os.getenv(env_var_name, str(default_port)))


def load_cli_environment(
    dotenv_path: str | None = None,
    *,
    log_prefix: str = "[CLI CONFIG]",
) -> str:
    """
    Load one CLI environment file using Fred's standard startup convention.

    Why this function exists:
    - Fred CLIs should resolve `ENV_FILE` and `CONFIG_FILE` the same way as the
      backend they are testing or operating

    How to use it:
    - call once at process startup before building the CLI parser
    - optionally pass an explicit env file path in tests

    Example:
    - `load_cli_environment()`
    """

    config_files = ConfigFiles(logger=logger, log_prefix=log_prefix)
    return config_files.load_environment(dotenv_path)


def load_configuration_yaml(path: Path) -> dict[str, Any] | None:
    """
    Load one backend configuration mapping when the file exists.

    Why this function exists:
    - CLI auth discovery should reuse the same backend configuration that
      developers already maintain

    How to use it:
    - pass the candidate config path and inspect the returned mapping, or
      `None` when the file does not exist

    Example:
    - `payload = load_configuration_yaml(Path("./config/configuration.yaml"))`
    """

    if not path.exists():
        return None
    payload = parse_yaml_mapping_file(str(path))
    return payload if isinstance(payload, dict) else None


def default_configuration_file(
    *,
    env_var_name: str = "CONFIG_FILE",
    default_path: str = "./config/configuration.yaml",
) -> Path:
    """
    Resolve the backend configuration file path used for CLI auth discovery.

    Why this function exists:
    - CLIs should honor the same `CONFIG_FILE` convention as their backend
      server counterpart

    How to use it:
    - keep the defaults when the backend uses standard `CONFIG_FILE`
    - override the env-var name only if a future CLI requires it

    Example:
    - `config_file = default_configuration_file()`
    """

    return Path(os.getenv(env_var_name, default_path))


def resolve_keycloak_login_config(
    *,
    realm_url: str | None,
    client_id: str | None,
    client_secret: str | None,
    config_file: Path | None = None,
    realm_env_var: str = "FRED_AGENT_KEYCLOAK_REALM_URL",
    client_id_env_var: str = "FRED_AGENT_KEYCLOAK_CLIENT_ID",
    client_secret_env_var: str = "FRED_AGENT_KEYCLOAK_CLIENT_SECRET",
) -> KeycloakLoginConfig | None:
    """
    Resolve CLI Keycloak login settings from flags, env vars, or backend config.

    Why this function exists:
    - Fred CLIs should auto-discover Keycloak settings from the same config as
      the backend they target, while still allowing explicit overrides

    How to use it:
    - pass optional explicit values from CLI flags
    - optionally override env-var names for non-runtime CLIs

    Example:
    - `cfg = resolve_keycloak_login_config(realm_url=None, client_id=None, client_secret=None, config_file=Path("./config/configuration.yaml"))`
    """

    resolved_realm_url = realm_url or os.getenv(realm_env_var)
    resolved_client_id = client_id or os.getenv(client_id_env_var)
    resolved_client_secret = client_secret or os.getenv(client_secret_env_var)

    payload = load_configuration_yaml(config_file or default_configuration_file())
    if isinstance(payload, dict):
        security = payload.get("security")
        if isinstance(security, dict):
            user_security = security.get("user")
            if isinstance(user_security, dict):
                if not user_security.get("enabled", True):
                    return None
                if resolved_realm_url is None:
                    raw_realm_url = user_security.get("realm_url")
                    if isinstance(raw_realm_url, str) and raw_realm_url.strip():
                        resolved_realm_url = raw_realm_url.strip()
                if resolved_client_id is None:
                    raw_client_id = user_security.get("client_id")
                    if isinstance(raw_client_id, str) and raw_client_id.strip():
                        resolved_client_id = raw_client_id.strip()

    if not resolved_realm_url or not resolved_client_id:
        return None

    return KeycloakLoginConfig(
        realm_url=resolved_realm_url,
        client_id=resolved_client_id,
        client_secret=resolved_client_secret,
    )


def build_cli_token_provider(
    *,
    auth_session: KeycloakUserSessionManager | None,
    static_token: str | None,
    log_prefix: str = "[chat]",
) -> Callable[[], str | None]:
    """
    Build the bearer-token provider used by one CLI HTTP client.

    Why this function exists:
    - Fred CLIs should reuse a cached Keycloak session when possible
    - an expired or revoked refresh token must not prevent the CLI from
      starting, because developers still need access to public endpoints and a
      way to recover with `/login`

    How to use it:
    - call once from the CLI entrypoint after resolving auth configuration
    - pass the returned callable into the backend-specific HTTP client

    Example:
    - `token_provider = build_cli_token_provider(auth_session=auth, static_token=None, log_prefix="[chat]")`
    """

    warned_about_cached_session = False

    def _provide_token() -> str | None:
        nonlocal warned_about_cached_session

        if auth_session is not None:
            try:
                token = auth_session.get_access_token()
            except (RuntimeError, httpx.HTTPError) as exc:
                if not warned_about_cached_session:
                    fallback_label = (
                        "the static bearer token" if static_token else "no bearer token"
                    )
                    print(
                        f"{log_prefix} auth warning: cached Keycloak session is no longer usable "
                        f"({exc}). Continuing with {fallback_label}. Use /login to authenticate again."
                    )
                    warned_about_cached_session = True
                token = None
            if token:
                return token
        return static_token

    return _provide_token
