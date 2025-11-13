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

import time
from typing import Callable, Optional, Union

import requests
from requests.auth import AuthBase


class ClientCredentialsProvider:
    """
    ClientCredentialsProvider is a utility class for securely obtaining and caching OAuth2 access tokens
    using the client credentials grant type, typically for service-to-service authentication.

    This provider is designed to be used by applications that need to invoke protected services
    using service accounts, such as microservices communicating with each other in a secure environment.

    Key Features:
    - Fetches access tokens from a Keycloak authorization server using the client credentials flow.
    - Caches the token in memory and automatically reuses it until shortly before expiry, minimizing
        unnecessary token requests and improving performance.
    - Supports optional audience specification for token scoping.
    - Allows configuration of SSL verification for HTTP requests.
    - Provides a method to force token refresh, invalidating the cached token.

    Usage:
    Instantiate the provider with the required Keycloak parameters (base URL, realm, client ID, and secret).
    Call the instance to obtain a valid access token for use in outbound requests to protected services.

    Example:
            provider = ClientCredentialsProvider(
                    keycloak_base="https://auth.example.com",
                    realm="myrealm",
                    client_id="service-app",
                    client_secret="supersecret",            #pragma: allowlist secret
                    audience="api-service"
            )
            token = provider()  # Returns a valid access token string

    Methods:
            __call__(): Returns a valid access token, fetching a new one if necessary.
            force_refresh(): Invalidates the cached token, forcing a refresh on next call.
    """

    def __init__(
        self,
        *,
        keycloak_base: str,
        realm: str,
        client_id: str,
        client_secret: str,
        audience: Optional[str] = None,
        verify: Optional[bool] = None,
    ):
        self.token_url = (
            f"{keycloak_base.rstrip('/')}/realms/{realm}/protocol/openid-connect/token"
        )
        self.client_id = client_id
        self.client_secret = client_secret
        self.audience = audience
        self.verify = verify
        self._tok: Optional[str] = None
        self._exp: float = 0.0

    def __call__(self) -> str:
        # reuse token until ~10s before expiry
        if self._tok and time.time() < self._exp:
            if self._tok is not None:
                return self._tok
            raise RuntimeError("Token is missing.")

        form = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if self.audience:
            form["audience"] = self.audience

        r = requests.post(self.token_url, data=form, timeout=10, verify=self.verify)
        if r.status_code >= 400:
            # Try to show Keycloak's error payload
            try:
                err = r.json()
            except Exception:
                err = {"error": r.text[:200]}
            raise RuntimeError(
                f"Keycloak token request failed "
                f"(status={r.status_code}, client_id={self.client_id}, realm_url={self.token_url}): "
                f"{err}"
            )
        payload = r.json()
        self._tok = payload["access_token"]
        self._exp = time.time() + max(0, int(payload.get("expires_in", 60)) - 10)
        if self._tok is not None:
            return self._tok
        raise RuntimeError("Failed to obtain access token.")

    def force_refresh(self) -> None:
        self._tok, self._exp = None, 0.0


class BearerAuth(AuthBase):
    """requests.Auth that injects Authorization: Bearer <token> using a provider/callable."""

    def __init__(self, token_provider: Union[str, Callable[[], str]]):
        self._provider = (
            (lambda: token_provider)
            if isinstance(token_provider, str)
            else token_provider
        )

    def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
        token = self._provider()
        if token:
            r.headers["Authorization"] = f"Bearer {token}"
        return r
