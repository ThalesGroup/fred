"""Build a first-party application's security profile from its environment."""

from __future__ import annotations

import json
import os

from pydantic import AnyHttpUrl, AnyUrl

from fred_core.security.delegation import DelegationConfig
from fred_core.security.structure import (
    M2MSecurity,
    OpenFgaRebacConfig,
    SecurityConfiguration,
    UserSecurity,
)

DELEGATION_ENV_DEFAULT = "FRED_DELEGATION"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set")
    return value


def _optional(name: str) -> str | None:
    return os.environ.get(name, "").strip() or None


def _delegation(env_name: str) -> DelegationConfig:
    """Read the whole delegation block from one structured value.

    Carrying the block rather than one variable per setting keeps a new field
    in it a deployment change instead of a code change in every application.
    """

    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return DelegationConfig()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{env_name} must be a JSON object") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{env_name} must be a JSON object")
    return DelegationConfig.model_validate(payload)


def security_configuration_from_env(
    *,
    m2m_secret_env: str,
    openfga_token_env: str,
    delegation_env: str = DELEGATION_ENV_DEFAULT,
) -> SecurityConfiguration:
    """The hardened profile a first-party application runs under.

    The caller supplies only the variable names that differ between
    applications; every other name is shared and read here.
    """

    user_realm_url = AnyUrl(_required("KEYCLOAK_REALM_URL"))
    # A browser token carries the address the person signed in at, a workload
    # token the address it was minted at. One value cannot validate both.
    workload_realm = _optional("KEYCLOAK_M2M_REALM_URL")
    # The secret is read by the token provider, not here; requiring it now turns
    # a missing credential into a startup failure rather than a first refused call.
    _ = _required(m2m_secret_env)
    return SecurityConfiguration(
        profile="c3",
        user=UserSecurity(
            enabled=True,
            realm_url=user_realm_url,
            client_id=_required("KEYCLOAK_USER_AUDIENCE"),
        ),
        m2m=M2MSecurity(
            enabled=True,
            realm_url=AnyUrl(workload_realm) if workload_realm else user_realm_url,
            client_id=_required("KEYCLOAK_M2M_CLIENT_ID"),
            audience=_optional("KEYCLOAK_M2M_AUDIENCE"),
            secret_env_var=m2m_secret_env,
        ),
        delegation=_delegation(delegation_env),
        rebac=OpenFgaRebacConfig(
            enabled=True,
            api_url=AnyHttpUrl(_required("OPENFGA_API_URL")),
            store_name=os.environ.get("OPENFGA_STORE_NAME", "fred"),
            authorization_model_id=_optional("OPENFGA_AUTHORIZATION_MODEL_ID"),
            # A first-party application reads the shared model and never owns it.
            create_store_if_needed=False,
            sync_schema_on_init=False,
            token_env_var=openfga_token_env,
            timeout_millisec=5000,
        ),
    )
