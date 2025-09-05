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
import requests
from typing import Optional, Callable, Union
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
                    client_secret="supersecret",
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


class TokenExchangeProvider:
    """
    OAuth2 Token Exchange provider for preserving user identity in service-to-service calls.
    
    This provider implements RFC 8693 Token Exchange to convert user access tokens 
    into service account tokens that preserve the original user's identity.
    This allows backend services to make authenticated calls on behalf of users
    while maintaining proper authorization and audit trails.
    
    Key Features:
    - Exchanges user tokens for service tokens with preserved identity
    - Caches exchanged tokens to minimize OAuth2 roundtrips
    - Thread-safe token management
    - Automatic token refresh when expired
    
    Usage:
    exchanger = TokenExchangeProvider(
        keycloak_base="https://auth.example.com",
        realm="myrealm", 
        client_id="agentic",
        client_secret="supersecret",
        audience="knowledge-flow"
    )
    service_token = exchanger.exchange_token(user_token)
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
        self._cache: dict = {}  # user_token_hash -> (exchanged_token, expiry)

    def exchange_token(self, user_token: str) -> str:
        """
        Exchange a user access token for a service token with preserved identity.
        
        Args:
            user_token: The original user's JWT access token
            
        Returns:
            A new JWT token that preserves user identity but has service permissions
            
        Raises:
            RuntimeError: If token exchange fails
        """
        if not user_token:
            raise RuntimeError("User token is required for token exchange")

        # Use a hash of the token for caching (avoid storing full token)
        import hashlib
        token_hash = hashlib.sha256(user_token.encode()).hexdigest()[:16]
        
        # Check cache
        if token_hash in self._cache:
            exchanged_token, exp = self._cache[token_hash]
            if time.time() < exp - 30:  # 30s buffer
                return exchanged_token

        # Perform token exchange
        form = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "subject_token": user_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        }
        if self.audience:
            form["audience"] = self.audience

        try:
            r = requests.post(self.token_url, data=form, timeout=10, verify=self.verify)
            if r.status_code >= 400:
                # Try to show Keycloak's error payload
                try:
                    err = r.json()
                except Exception:
                    err = {"error": r.text[:200]}
                raise RuntimeError(
                    f"Token exchange failed "
                    f"(status={r.status_code}, client_id={self.client_id}): "
                    f"{err}"
                )
            
            payload = r.json()
            exchanged_token = payload.get("access_token")
            expires_in = int(payload.get("expires_in", 300))
            
            if not exchanged_token:
                raise RuntimeError("Token exchange did not return an access token")
            
            # Cache the result
            exp_time = time.time() + expires_in
            self._cache[token_hash] = (exchanged_token, exp_time)
            
            return exchanged_token
            
        except requests.RequestException as e:
            raise RuntimeError(f"Token exchange request failed: {e}")

    def clear_cache(self) -> None:
        """Clear the token cache."""
        self._cache.clear()


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
