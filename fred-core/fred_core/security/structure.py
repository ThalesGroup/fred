from typing import Protocol
from pydantic import BaseModel


class KeycloakUser(BaseModel):
    """Represents an authenticated Keycloak user."""

    uid: str
    username: str
    roles: list[str]
    email: str | None = None


class Security(BaseModel):
    enabled: bool
    keycloak_url: str
    client_id: str
    authorized_origins: list[str]


class ConfigurationWithSecurity(Protocol):
    security: Security
