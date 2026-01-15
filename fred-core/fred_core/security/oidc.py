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

import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import jwt
from fastapi import HTTPException, Security
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWKClient

from fred_core.common.lru_cache import ThreadSafeLRUCache
from fred_core.security.structure import KeycloakUser, UserSecurity

logger = logging.getLogger(__name__)

# --- runtime toggles ------------------
STRICT_ISSUER = os.getenv("FRED_STRICT_ISSUER", "false").lower() in ("1", "true", "yes")
STRICT_AUDIENCE = os.getenv("FRED_STRICT_AUDIENCE", "false").lower() in (
    "1",
    "true",
    "yes",
)
CLOCK_SKEW_SECONDS = int(os.getenv("FRED_JWT_CLOCK_SKEW", "0"))  # optional leeway
JWT_CACHE_ENABLED = os.getenv("FRED_JWT_CACHE_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)
JWT_CACHE_TTL_SECONDS = int(os.getenv("FRED_JWT_CACHE_TTL", "60"))
JWT_CACHE_MAX_SIZE = int(os.getenv("FRED_JWT_CACHE_SIZE", "512"))

# Initialize global variables (to be set later)
KEYCLOAK_ENABLED = False
KEYCLOAK_URL = ""
KEYCLOAK_JWKS_URL = ""
KEYCLOAK_CLIENT_ID = ""
_JWKS_CLIENT: PyJWKClient | None = None  # cached for perf
_JWT_CACHE: ThreadSafeLRUCache[str, tuple[float, KeycloakUser]] = ThreadSafeLRUCache(
    JWT_CACHE_MAX_SIZE
)


def _b64json(data: str) -> Dict[str, Any]:
    try:
        # add padding if missing
        padded = data + "=" * (-len(data) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return {}


def _peek_header_and_claims(token: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    try:
        h, p, _ = token.split(".")
        return _b64json(h), _b64json(p)
    except Exception:
        return {}, {}


def _iso(ts: int | float | None) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except Exception:
        return None


def get_keycloak_url() -> str:
    """
    Returns the globally initialized Keycloak Realm URL (e.g., http://host:port/realms/app).
    """
    if not KEYCLOAK_URL:
        # This state should not be hit if initialize_user_security ran at startup
        logger.warning("[SECURITY] Keycloak URL requested but not initialized.")
        return ""
    return KEYCLOAK_URL


def get_keycloak_client_id() -> str:
    """
    Returns the globally initialized Keycloak Client ID.
    """
    if not KEYCLOAK_CLIENT_ID:
        # This state should not be hit if initialize_user_security ran at startup
        logger.warning("[SECURITY] Keycloak Client ID requested but not initialized.")
        return ""
    return KEYCLOAK_CLIENT_ID


def initialize_user_security(config: UserSecurity):
    """
    Initialize the Keycloak authentication settings from the given configuration.
    """
    global \
        KEYCLOAK_ENABLED, \
        KEYCLOAK_URL, \
        KEYCLOAK_JWKS_URL, \
        KEYCLOAK_CLIENT_ID, \
        _JWKS_CLIENT

    KEYCLOAK_ENABLED = config.enabled
    KEYCLOAK_URL = str(config.realm_url).rstrip("/")
    KEYCLOAK_CLIENT_ID = config.client_id
    KEYCLOAK_JWKS_URL = f"{KEYCLOAK_URL}/protocol/openid-connect/certs"
    _JWKS_CLIENT = None  # reset; will lazy-create on first decode

    # derive base + realm for log clarity
    base, realm = split_realm_url(KEYCLOAK_URL)
    logger.info(
        "[SECURITY] Keycloak initialized: enabled=%s base=%s realm=%s client_id=%s jwks=%s strict_issuer=%s strict_audience=%s skew=%ss",
        KEYCLOAK_ENABLED,
        base,
        realm,
        KEYCLOAK_CLIENT_ID,
        KEYCLOAK_JWKS_URL,
        STRICT_ISSUER,
        STRICT_AUDIENCE,
        CLOCK_SKEW_SECONDS,
    )


def split_realm_url(realm_url: str) -> tuple[str, str]:
    """
    Split a Keycloak realm URL like:
      http://host:port/realms/<realm>
    into (base, realm).
    """
    u = realm_url.rstrip("/")
    marker = "/realms/"
    idx = u.find(marker)
    if idx == -1:
        raise ValueError(
            f"Invalid keycloak_url (expected .../realms/<realm>): {realm_url}"
        )
    base = u[:idx]
    realm = u[idx + len(marker) :].split("/", 1)[0]
    return base, realm


# OAuth2 Password Bearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


def _get_jwks_client() -> PyJWKClient:
    global _JWKS_CLIENT
    if _JWKS_CLIENT is None:
        logger.debug("[SECURITY] Creating PyJWKClient for %s", KEYCLOAK_JWKS_URL)
        _JWKS_CLIENT = PyJWKClient(KEYCLOAK_JWKS_URL)
    return _JWKS_CLIENT


def _get_cached_user(token: str) -> KeycloakUser | None:
    if not JWT_CACHE_ENABLED or not token:
        return None

    entry = _JWT_CACHE.get(token)
    if entry is None:
        return None

    expires_at, user = entry
    now = time.time()
    if expires_at > now:
        logger.debug(
            "[SECURITY] JWT cache hit for subject=%s (expires_at=%s)",
            user.uid,
            _iso(expires_at),
        )
        return user

    # stale entry
    _JWT_CACHE.delete(token)
    return None


def _cache_user(token: str, payload: Dict[str, Any], user: KeycloakUser) -> None:
    if not JWT_CACHE_ENABLED or JWT_CACHE_MAX_SIZE <= 0:
        return

    now = time.time()
    token_exp = payload.get("exp")
    ttl_exp = now + JWT_CACHE_TTL_SECONDS if JWT_CACHE_TTL_SECONDS > 0 else None

    # pick the earliest non-null expiry between token exp and TTL
    expires_at_candidates: list[float] = []
    for candidate in (token_exp, ttl_exp):
        if candidate is None:
            continue
        try:
            expires_at_candidates.append(float(candidate))
        except (TypeError, ValueError) as exc:
            logger.debug(
                "[SECURITY] Ignoring invalid expiry candidate %s (%s)", candidate, exc
            )

    if not expires_at_candidates:
        return

    expires_at = min(expires_at_candidates)
    if expires_at <= now:
        return

    _JWT_CACHE.set(token, (expires_at, user))


def decode_jwt(token: str) -> KeycloakUser:
    """Decodes a JWT token using PyJWT and retrieves user information with rich diagnostics."""
    if not KEYCLOAK_ENABLED:
        logger.debug("[SECURITY] Authentication is DISABLED. Returning a mock user.")
        return KeycloakUser(
            uid="admin", username="admin", roles=["admin"], email="dev@localhost", groups=["admins"]
        )

    cached_user = _get_cached_user(token)
    if cached_user:
        return cached_user

    # quick header/claim peek for logs (never log raw token)
    header, payload_peek = _peek_header_and_claims(token)
    kid = header.get("kid")
    alg = header.get("alg")
    logger.debug(
        "JWT peek: kid=%s alg=%s iss=%s aud=%s azp=%s sub=%s exp=%s(%s) nbf=%s(%s)",
        kid,
        alg,
        payload_peek.get("iss"),
        payload_peek.get("aud"),
        payload_peek.get("azp"),
        payload_peek.get("sub"),
        payload_peek.get("exp"),
        _iso(payload_peek.get("exp")),
        payload_peek.get("nbf"),
        _iso(payload_peek.get("nbf")),
    )

    # Soft checks (warn-only unless STRICT_* enabled)
    iss = payload_peek.get("iss")
    aud = payload_peek.get("aud")
    if iss and KEYCLOAK_URL and not str(iss).startswith(KEYCLOAK_URL):
        logger.warning(
            "[SECURITY] JWT issuer mismatch (soft): iss=%s expected_prefix=%s",
            iss,
            KEYCLOAK_URL,
        )
        if STRICT_ISSUER:
            raise HTTPException(status_code=401, detail="Invalid token issuer")

    if KEYCLOAK_CLIENT_ID:
        aud_list = aud if isinstance(aud, list) else [aud] if aud else []
        if KEYCLOAK_CLIENT_ID not in aud_list:
            logger.debug(
                "[SECURITY] JWT audience does not include client_id (soft): aud=%s client_id=%s",
                aud_list,
                KEYCLOAK_CLIENT_ID,
            )
            if STRICT_AUDIENCE:
                raise HTTPException(status_code=401, detail="Invalid token audience")

    # JWKS fetch + decode
    try:
        t0 = time.perf_counter()
        jwks_client = _get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token).key
        jwks_ms = (time.perf_counter() - t0) * 1000
        logger.debug("[SECURITY] JWKS resolved key in %.1f ms (kid=%s)", jwks_ms, kid)
    except Exception as e:
        # Invalid JWT structure/kid/signature is a normal 401, not a 500.
        logger.warning("[SECURITY] Could not retrieve signing key from JWKS: %s", e)
        raise HTTPException(
            status_code=401,
            detail="Invalid token signature",
            headers={"WWW-Authenticate": "Bearer error='invalid_token'"},
        )

    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            options={
                "verify_exp": True,
                "verify_aud": False,
            },  # we do soft aud check above
            leeway=CLOCK_SKEW_SECONDS,
        )
        logger.debug("[SECURITY] JWT token successfully decoded")
    except jwt.ExpiredSignatureError:
        logger.warning("[SECURITY] Access token expired")
        raise HTTPException(
            status_code=401,
            detail="Token has expired",
            headers={
                "WWW-Authenticate": "Bearer error='invalid_token', error_description='token expired'"
            },
        )
    except jwt.InvalidTokenError as e:
        logger.error("[SECURITY] Invalid JWT token: %s", e)
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer error='invalid_token'"},
        )

    # Extract client roles
    client_roles = []
    if "resource_access" in payload:
        client_data = payload["resource_access"].get(KEYCLOAK_CLIENT_ID, {})
        client_roles = client_data.get("roles", [])

    logger.info(
        "[SECURITY] JWT token decoded: sub=%s preferred_username=%s email=%s roles=%s",
        payload.get("sub"),
        payload.get("preferred_username"),
        payload.get("email"),
        client_roles,
    )

    # Build user
    user = KeycloakUser(
        uid=payload.get("sub"),
        username=payload.get("preferred_username", ""),
        roles=client_roles,
        email=payload.get("email"),
        groups=payload.get("groups", []),
    )
    logger.debug("KeycloakUser built: %s", user)
    _cache_user(token, payload, user)
    return user


def get_current_user(token: str = Security(oauth2_scheme)) -> KeycloakUser:
    """Fetches the current user from Keycloak token with robust diagnostics."""
    if not KEYCLOAK_ENABLED:
        logger.debug("[SECURITY] Authentication is DISABLED. Returning a mock user.")
        return KeycloakUser(
            uid="admin", username="admin", roles=["admin"], email="admin@mail.com", groups=["admins"]
        )

    if not token:
        logger.warning("No Bearer token provided on secured endpoint")
        raise HTTPException(
            status_code=401,
            detail="No authentication token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # do NOT log the full token
    logger.debug("[SECURITY] Received token prefix: %s...", token[:10])
    return decode_jwt(token)
