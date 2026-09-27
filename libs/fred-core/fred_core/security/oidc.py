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
import getpass
import json
import logging
import os
import time
from typing import Any, Dict, Tuple
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWKClient

from fred_core.common import ThreadSafeLRUCache, get_config, read_env_bool
from fred_core.security.delegation import (
    AssertedUser,
    bears_service_account_markers,
    get_delegation_config,
    initialize_delegation,
    is_user_client,
    read_caller_roles,
    resolve_delegated_principal,
)
from fred_core.security.structure import (
    LOCAL_DEV_CLIENT_ID,
    KeycloakUser,
    PrincipalContext,
    SecurityConfiguration,
    UserSecurity,
    is_service_agent,
)
from fred_core.security.whitelist_access_control.access_control import (
    is_principal_whitelisted,
    is_whitelist_active,
)

from ..users.store import BaseUserStore
from ..users.store.postgres_user_store import get_user_store

logger = logging.getLogger(__name__)

# --- runtime toggles ------------------
STRICT_ISSUER = read_env_bool("FRED_STRICT_ISSUER", default=False)
STRICT_AUDIENCE = read_env_bool("FRED_STRICT_AUDIENCE", default=False)
CLOCK_SKEW_SECONDS = int(os.getenv("FRED_JWT_CLOCK_SKEW", "0"))  # optional leeway
JWT_CACHE_ENABLED = read_env_bool("FRED_JWT_CACHE_ENABLED", default=True)
JWT_CACHE_TTL_SECONDS = int(os.getenv("FRED_JWT_CACHE_TTL", "60"))
JWT_CACHE_MAX_SIZE = int(os.getenv("FRED_JWT_CACHE_SIZE", "512"))
# Application-side ceiling on token lifetime (exp - iat), independent of
# whatever an IdP was configured to issue. Unlike STRICT_ISSUER/STRICT_AUDIENCE
# (opt-in, gated behind the c3 profile, never enabled by any config in this
# repo), this stays on by default: a misconfigured or unfamiliar IdP issuing
# long-lived tokens should not be silently trusted. Fred's own M2M provider
# (`backend_to_backend_auth.py`) already mints short-lived, auto-refreshed
# tokens per call, so this does not affect normal service-to-service traffic
# — raise the env var if a deployment genuinely needs a longer ceiling.
MAX_TOKEN_LIFETIME_SECONDS = int(os.getenv("FRED_JWT_MAX_LIFETIME_SECONDS", "3600"))

# Initialize global variables (to be set later)
KEYCLOAK_ENABLED = False
KEYCLOAK_URL = ""
KEYCLOAK_JWKS_URL = ""
KEYCLOAK_CLIENT_ID = ""
# Every address the realm is configured under: tokens minted at the machine-to-
# machine address carry that issuer. Set by apply_security_profile.
_REALM_ISSUERS: frozenset[str] = frozenset()
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


def get_keycloak_url() -> str:
    """
    Returns the globally initialized Keycloak Realm URL (e.g., http://host:port/realms/app).
    """
    if not KEYCLOAK_URL:
        # This state should not be hit if initialize_user_security ran at startup
        logger.warning("[AUTH] Keycloak URL requested but not initialized.")
        return ""
    return KEYCLOAK_URL


def get_keycloak_client_id() -> str:
    """
    Returns the globally initialized Keycloak Client ID.
    """
    if not KEYCLOAK_CLIENT_ID:
        # This state should not be hit if initialize_user_security ran at startup
        logger.warning("[AUTH] Keycloak Client ID requested but not initialized.")
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
        "[AUTH] Keycloak initialized: enabled=%s base=%s realm=%s client_id=%s jwks=%s strict_issuer=%s strict_audience=%s skew=%ss",
        KEYCLOAK_ENABLED,
        base,
        realm,
        KEYCLOAK_CLIENT_ID,
        KEYCLOAK_JWKS_URL,
        STRICT_ISSUER,
        STRICT_AUDIENCE,
        CLOCK_SKEW_SECONDS,
    )


def apply_security_profile(config: SecurityConfiguration) -> None:
    """
    Enforce a hardened security profile at startup (RUNTIME-07 rev. 2, F5/F6).

    When ``security.profile == 'c3'``:
    - force strict JWT issuer + audience validation (closes F5 soft defaults),
    - require user + m2m auth enabled — no no-security / mock-admin (F6),
    - require ReBAC (OpenFGA) enabled, so the pod authorizes every request and
      fails closed (no permissive Noop engine).

    The control-plane issues NO signed grant; authorization is decided at the pod
    by a Keycloak JWT + OpenFGA check. Raises ValueError on any violation so the
    service FAILS CLOSED — it refuses to start in an insecure configuration rather
    than silently degrading.

    Installs ``security.delegation`` for the shared user dependency under every
    profile; the profile enforcement itself is a no-op for any non-c3 profile
    (dev behavior unchanged).
    """
    global STRICT_ISSUER, STRICT_AUDIENCE, _REALM_ISSUERS

    from fred_pod.security.backend_to_backend_auth import set_token_observer

    from fred_core.security.auth_metrics import observe_m2m

    set_token_observer(observe_m2m)

    _REALM_ISSUERS = frozenset(
        str(url).rstrip("/") for url in (config.user.realm_url, config.m2m.realm_url)
    )
    # Every backend hands the whole security block to this one startup hook, so the
    # delegation block is installed here too — before the profile check returns.
    initialize_delegation(
        config.delegation,
        issuers=_REALM_ISSUERS,
        user_clients=[config.user.client_id],
    )

    if config.profile != "c3":
        return

    STRICT_ISSUER = True
    STRICT_AUDIENCE = True

    violations: list[str] = []
    if not config.user.enabled:
        violations.append(
            "security.user.enabled must be true (no-security/mock-admin is forbidden)"
        )
    if not config.m2m.enabled:
        violations.append("security.m2m.enabled must be true")
    rebac = config.rebac
    if rebac is None or not rebac.enabled:
        violations.append(
            "security.rebac.enabled must be true (pod-side OpenFGA authorization "
            "is mandatory and must fail closed)"
        )

    if violations:
        raise ValueError(
            "C3 security profile violations (refusing to start): "
            + "; ".join(violations)
        )

    logger.info(
        "[AUTH] C3 profile active: strict issuer+audience, OpenFGA ReBAC enforced"
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
        logger.debug("[AUTH] Creating PyJWKClient for %s", KEYCLOAK_JWKS_URL)
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
        logger.debug("[AUTH] JWT cache hit")
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
                "[AUTH] Ignoring invalid expiry candidate %s (%s)", candidate, exc
            )

    if not expires_at_candidates:
        return

    expires_at = min(expires_at_candidates)
    if expires_at <= now:
        return

    _JWT_CACHE.set(token, (expires_at, user))


def _parse_user_uuid(user: KeycloakUser) -> UUID | None:
    """
    Return the Keycloak subject as a UUID when the deployment uses UUID subjects.

    Why this function exists:
    - GCU enforcement now relies on the shared `fred_core.users` store keyed by
      UUID
    - no-security mode still injects a mock admin user with `uid="admin"`, and
      that mock subject must not be forced into the persisted user store path

    How to use it:
    - call before GCU store reads or writes; handle `None` according to the
      current security mode

    Example:
    - `user_uuid = _parse_user_uuid(user)`
    """
    try:
        return UUID(user.uid)
    except ValueError:
        return None


def _token_audiences(value: object) -> frozenset[str]:
    if isinstance(value, str) and value:
        return frozenset({value})
    if isinstance(value, list):
        return frozenset(item for item in value if isinstance(item, str) and item)
    return frozenset()


def decode_jwt(token: str) -> KeycloakUser:
    """Decodes a JWT token using PyJWT and retrieves user information with rich diagnostics."""
    if not KEYCLOAK_ENABLED:
        username = getpass.getuser()
        logger.debug(
            "[AUTH] Authentication is DISABLED. Returning mock user: %s", username
        )
        # Carries a client id so routes gated on ONE exact client stay reachable
        # locally, but deliberately NOT the service_agent role: granting it here
        # would flip every `is_service_agent` bypass — team reads, runtime
        # execution, tag and tabular access — for every local caller, and a
        # per-team authorization regression would stop failing in development.
        return KeycloakUser(
            uid=username,
            username=username,
            roles=["admin"],
            email=f"{username}@localhost",
            client_id=LOCAL_DEV_CLIENT_ID,
        )

    cached_user = _get_cached_user(token)
    if cached_user:
        return cached_user

    # quick header/claim peek for logs (never log raw token)
    header, payload_peek = _peek_header_and_claims(token)
    alg = header.get("alg")
    logger.debug("[AUTH] JWT header parsed algorithm=%s", alg)

    # Soft observability logs only. Strict enforcement (C3) happens in jwt.decode
    # below, on the SIGNATURE-VERIFIED payload, via exact issuer/audience.
    iss = payload_peek.get("iss")
    aud = payload_peek.get("aud")
    if iss and KEYCLOAK_URL and str(iss) != KEYCLOAK_URL:
        logger.warning("[AUTH] JWT issuer mismatch (soft)")
    if KEYCLOAK_CLIENT_ID:
        aud_list = aud if isinstance(aud, list) else [aud] if aud else []
        if KEYCLOAK_CLIENT_ID not in aud_list:
            logger.debug("[AUTH] JWT audience does not include the configured client")

    # JWKS fetch + decode
    try:
        t0 = time.perf_counter()
        jwks_client = _get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token).key
        jwks_ms = (time.perf_counter() - t0) * 1000
        logger.debug("[AUTH] JWKS resolved key in %.1f ms", jwks_ms)
    except Exception:
        # Invalid JWT structure/kid/signature is a normal 401, not a 500.
        logger.warning("[AUTH] Could not retrieve a trusted JWT signing key")
        raise HTTPException(
            status_code=401,
            detail="Invalid token signature",
            headers={"WWW-Authenticate": "Bearer error='invalid_token'"},
        )

    # Under the C3 profile, STRICT_AUDIENCE/STRICT_ISSUER are set: PyJWT then
    # enforces exact audience (== client_id) and exact issuer (a realm address) on the
    # verified payload, and rejects a confused `alg` (algorithms pinned to RS256).
    # In dev (soft) we keep verification of signature + expiry only.
    verify_aud = bool(STRICT_AUDIENCE and KEYCLOAK_CLIENT_ID)
    delegation = get_delegation_config()
    expected_audience: list[str] | None = None
    if verify_aud:
        # A delegating workload is addressed to the delegation audience, not to
        # this service's login client; the caller role is required for it below.
        expected_audience = [KEYCLOAK_CLIENT_ID]
        if delegation.accept_delegated_calls:
            expected_audience.append(delegation.audience)
    expected_issuer: list[str] | None = (
        sorted(_REALM_ISSUERS | {KEYCLOAK_URL})
        if (STRICT_ISSUER and KEYCLOAK_URL)
        else None
    )
    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=expected_audience,
            issuer=expected_issuer,
            options={"verify_exp": True, "verify_aud": verify_aud},
            leeway=CLOCK_SKEW_SECONDS,
        )
        logger.debug("[AUTH] JWT token successfully decoded")
    except jwt.ExpiredSignatureError:
        logger.warning("[AUTH] Access token expired")
        raise HTTPException(
            status_code=401,
            detail="Token has expired",
            headers={
                "WWW-Authenticate": "Bearer error='invalid_token', error_description='token expired'"
            },
        )
    except jwt.InvalidTokenError:
        logger.error("[AUTH] Invalid JWT token")
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer error='invalid_token'"},
        )

    # Defense-in-depth ceiling on token lifetime, independent of the issuing
    # IdP's own configuration (see MAX_TOKEN_LIFETIME_SECONDS docstring above).
    # `verify_exp` above only rejects a token that has already expired; this
    # additionally rejects one that was never supposed to live this long in
    # the first place, regardless of whether it currently happens to still be
    # valid.
    iat, exp = payload.get("iat"), payload.get("exp")
    if isinstance(iat, (int, float)) and isinstance(exp, (int, float)):
        lifetime_seconds = exp - iat
        if lifetime_seconds < 0:
            # `verify_exp` above only checks exp against "now" — it does not
            # relate exp to iat, so a token claiming iat after its own exp
            # (malformed, or a confused/misconfigured IdP) can still pass it
            # as long as exp itself is still in the future. That negative
            # lifetime would otherwise fail the ">" ceiling check below
            # silently instead of being rejected.
            logger.warning("[AUTH] JWT has negative lifetime")
            raise HTTPException(
                status_code=401,
                detail="Token has invalid iat/exp claims",
                headers={
                    "WWW-Authenticate": "Bearer error='invalid_token', error_description='exp before iat'"
                },
            )
        if lifetime_seconds > MAX_TOKEN_LIFETIME_SECONDS:
            logger.warning("[AUTH] JWT lifetime exceeds policy ceiling")
            raise HTTPException(
                status_code=401,
                detail="Token lifetime exceeds the maximum permitted duration",
                headers={
                    "WWW-Authenticate": "Bearer error='invalid_token', error_description='token lifetime too long'"
                },
            )

    # Extract client roles
    client_roles = []
    if "resource_access" in payload:
        client_data = payload["resource_access"].get(KEYCLOAK_CLIENT_ID, {})
        client_roles = client_data.get("roles", [])
    caller_roles = read_caller_roles(payload)
    # Keycloak names the client in azp; RFC 9068 access tokens in client_id.
    client_id = payload.get("azp") or payload.get("client_id")
    service_account = bears_service_account_markers(payload, client_id)

    audiences = _token_audiences(payload.get("aud"))
    if verify_aud and KEYCLOAK_CLIENT_ID not in audiences:
        # Admitted on the delegation audience alone: only a delegating workload may be.
        if (
            delegation.caller_role not in caller_roles
            or is_user_client(client_id)
            or (delegation.service_accounts_only and not service_account)
        ):
            logger.warning("[AUTH] JWT audience accepted only for delegating workloads")
            raise HTTPException(
                status_code=401,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer error='invalid_token'"},
            )

    logger.debug("[AUTH] JWT token decoded")

    # Build user
    sub = payload.get("sub")
    if not isinstance(sub, str):
        logger.warning("[AUTH] JWT token missing or invalid subject claim")
        raise HTTPException(
            status_code=401,
            detail="Invalid token claims",
            headers={"WWW-Authenticate": "Bearer error='invalid_token'"},
        )

    user = KeycloakUser(
        uid=sub,
        username=payload.get("preferred_username", ""),
        roles=client_roles,
        email=payload.get("email"),
        client_id=client_id,
        token_issuer=payload.get("iss"),
        token_audiences=audiences,
        token_type=payload.get("typ"),
        caller_roles=caller_roles,
        service_account=service_account,
    )
    logger.debug("[AUTH] Authenticated principal built")
    _cache_user(token, payload, user)
    return user


async def _enforce_gcu(
    user: KeycloakUser, user_store: BaseUserStore, configuration
) -> KeycloakUser:
    """Refuse `user` unless the configured GCU version is persisted as accepted."""
    if configuration.app.gcu_version is None or not KEYCLOAK_ENABLED:
        return user

    user_uuid = _parse_user_uuid(user)
    if user_uuid is None:
        logger.warning(
            "[AUTH] Authenticated subject %r is not UUID-backed; rejecting GCU lookup.",
            user.uid,
        )
        raise HTTPException(status_code=403, detail="user_not_accept_gcu")

    user_details = await user_store.find_user_by_id(user_uuid)

    accepted_gcu_version = (
        user_details.gcuVersionAccepted.value
        if user_details is not None and user_details.gcuVersionAccepted is not None
        else None
    )

    if accepted_gcu_version != configuration.app.gcu_version:
        raise HTTPException(status_code=403, detail="user_not_accept_gcu")
    return user


async def get_current_user(
    request: Request,
    token: str = Security(oauth2_scheme),
    user_store: BaseUserStore = Depends(get_user_store),
    configuration=Depends(get_config),
) -> KeycloakUser | AssertedUser:
    """
    Return the authenticated user and enforce persisted GCU acceptance when enabled.

    Why this function exists:
    - secured deployments must gate access on the configured GCU version
    - no-security mode still needs a lightweight mock admin without requiring a
      UUID-backed persisted user row

    How to use it:
    - use as the default dependency for endpoints that require a fully admitted
      user; pair with `get_current_user_without_gcu()` for the `/gcu` acceptance
      flow itself

    Example:
    - `user: KeycloakUser = Depends(get_current_user)`
    """
    user = await get_current_user_without_gcu(request, token)
    if isinstance(user, AssertedUser):
        # The person's acceptance was gated by their own token when the run was
        # admitted; the workload speaking for them has no acceptance row of its own.
        return user
    return await _enforce_gcu(user, user_store, configuration)


async def get_current_user_or_service(
    request: Request,
    token: str = Security(oauth2_scheme),
    user_store: BaseUserStore = Depends(get_user_store),
    configuration=Depends(get_config),
) -> KeycloakUser | AssertedUser:
    """Admit a service identity without the GCU gate: a workload cannot accept
    terms, so the human admission rule does not apply to it (ReBAC still does).
    Any other caller goes through exactly `get_current_user`'s gate."""
    user = await get_current_user_without_gcu(request, token)
    if isinstance(user, AssertedUser):
        return user
    if is_service_agent(user):
        return user
    return await _enforce_gcu(user, user_store, configuration)


async def get_current_user_without_gcu(
    request: Request,
    token: str = Security(oauth2_scheme),
) -> KeycloakUser | AssertedUser:
    """Fetches the current user from Keycloak token with robust diagnostics.

    Returns an `AssertedUser` instead when this backend accepts delegated calls and a
    caller holding the delegation caller role presented a whole grant beside its own
    verified bearer.
    """
    if not KEYCLOAK_ENABLED:
        logger.debug("[AUTH] Authentication is DISABLED. Returning a mock user.")
        # Same local-dev client id as `decode_jwt`'s mock, and for the same
        # reason: this is the branch routes actually reach when authentication
        # is off, so without it every route gated on one exact client — machine
        # synchronization among them — is unreachable on a local stack.
        user = KeycloakUser(
            uid="admin",
            username="admin",
            roles=["admin"],
            email="admin@mail.com",
            client_id=LOCAL_DEV_CLIENT_ID,
        )
        request.state.principal_context = PrincipalContext(caller=user, subject=user)
        return user

    if not token:
        logger.warning("No Bearer token provided on secured endpoint")
        raise HTTPException(
            status_code=401,
            detail="No authentication token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.debug("[AUTH] Received bearer credential")
    caller = decode_jwt(token)
    return await resolve_request_principal(request, caller)


async def resolve_request_principal(
    request: Request,
    caller: KeycloakUser,
    *,
    query_only: bool = False,
) -> KeycloakUser | AssertedUser:
    asserted = await resolve_delegated_principal(request, caller, query_only=query_only)
    subject = asserted or caller
    if is_whitelist_active() and not is_principal_whitelisted(subject):
        logger.warning("[AUTH] Request subject is not in the whitelist")
        raise HTTPException(status_code=403, detail="user_not_whitelisted")
    request.state.principal_context = PrincipalContext(caller=caller, subject=subject)
    return subject


async def get_principal_context(
    request: Request,
    subject: KeycloakUser | AssertedUser = Depends(get_current_user),
) -> PrincipalContext:
    """Return the bearer caller and authorization subject for this request."""

    context = getattr(request.state, "principal_context", None)
    if isinstance(context, PrincipalContext):
        return context
    if not isinstance(subject, KeycloakUser):
        raise HTTPException(status_code=403, detail="principal_context_unavailable")
    return PrincipalContext(caller=subject, subject=subject)


async def require_own_credential(
    user: KeycloakUser | AssertedUser = Depends(get_current_user),
) -> KeycloakUser:
    """Dependency for an operation that a caller may not perform for someone else.

    An asserted person presented no credential of their own, so anything that acts
    on that person's behalf beyond a permission check must refuse them.
    """
    if isinstance(user, AssertedUser):
        logger.warning(
            "[AUTH] Asserted principal refused on an operation that requires its own credential"
        )
        raise HTTPException(status_code=403, detail="requires_own_credential")
    return user
