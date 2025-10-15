import logging
import os

from fred_core import split_realm_url
from keycloak import KeycloakAdmin

from app.application_context import get_configuration

logger = logging.getLogger(__name__)


def create_keycloak_admin() -> KeycloakAdmin | None:
    """Create a Keycloak admin client using the configured service account. Returns None if M2M security is not enabled."""
    config = get_configuration()
    m2m_security = config.security.m2m
    if not m2m_security or not m2m_security.enabled:
        return None

    client_secret = os.getenv("KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET")
    if not client_secret:
        raise RuntimeError("KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET is not set; cannot reconcile groups.")

    try:
        server_url, realm = split_realm_url(str(m2m_security.realm_url))
    except ValueError as exc:
        raise RuntimeError("Invalid Keycloak realm URL configured; cannot reconcile groups.") from exc

    return KeycloakAdmin(
        server_url=_ensure_trailing_slash(server_url),
        realm_name=realm,
        client_id=m2m_security.client_id,
        client_secret_key=client_secret,
        user_realm_name=realm,
    )


def _ensure_trailing_slash(url: str) -> str:
    return url if url.endswith("/") else f"{url}/"
