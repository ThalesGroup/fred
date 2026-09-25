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

"""Resolve token and JWKS endpoints once when a pod starts."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import httpx
from pydantic import AnyHttpUrl, ValidationError


@dataclass(frozen=True)
class OidcEndpoints:
    issuer: str
    jwks_uri: str
    token_endpoint: str


@lru_cache(maxsize=128)
def resolve_endpoints(
    *,
    provider: str,
    realm_url: str,
    jwks_url: str | None = None,
    token_url: str | None = None,
    timeout_seconds: float = 5.0,
) -> OidcEndpoints:
    """Resolve startup endpoints, using discovery only for generic OIDC providers.

    Pass the configured issuer as ``realm_url``; explicit endpoint URLs override
    discovery, while Keycloak retains its existing constructed URLs.
    """
    if provider == "keycloak":
        return OidcEndpoints(
            issuer=realm_url,
            jwks_uri=jwks_url or f"{realm_url}/protocol/openid-connect/certs",
            token_endpoint=token_url or f"{realm_url}/protocol/openid-connect/token",
        )
    if provider != "oidc":
        raise ValueError(f"Unsupported identity provider: {provider}")

    issuer = realm_url.rstrip("/")
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    try:
        response = httpx.get(discovery_url, timeout=timeout_seconds)
    except httpx.RequestError as exc:
        raise RuntimeError(
            f"OIDC discovery failed for issuer {issuer}: {type(exc).__name__}"
        ) from exc
    if response.status_code != 200:
        raise RuntimeError(
            f"OIDC discovery failed for issuer {issuer}: HTTP {response.status_code}"
        )
    try:
        document = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"OIDC discovery returned invalid JSON for {issuer}"
        ) from exc
    if not isinstance(document, dict):
        raise RuntimeError(f"OIDC discovery returned an invalid document for {issuer}")

    discovered_issuer = document.get("issuer")
    if not isinstance(discovered_issuer, str) or not discovered_issuer:
        raise RuntimeError(f"OIDC discovery did not provide an issuer for {issuer}")
    if discovered_issuer.rstrip("/") != issuer:
        raise RuntimeError(
            f"OIDC issuer mismatch: configured {issuer}, discovered {discovered_issuer}"
        )

    jwks_uri = jwks_url or document.get("jwks_uri")
    token_endpoint = token_url or document.get("token_endpoint")
    for name, value in (("jwks_uri", jwks_uri), ("token_endpoint", token_endpoint)):
        if not isinstance(value, str) or not value:
            raise RuntimeError(f"OIDC discovery did not provide {name} for {issuer}")
        try:
            AnyHttpUrl(value)
        except ValidationError as exc:
            raise RuntimeError(
                f"OIDC discovery returned an invalid {name} for {issuer}"
            ) from exc
    return OidcEndpoints(
        issuer=issuer,
        jwks_uri=jwks_uri,
        token_endpoint=token_endpoint,
    )
