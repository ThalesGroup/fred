from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class KeycloakM2MUserOperationDisabledError(Exception):
    """Raised when Keycloak M2M client is disabled for user operations."""

    def __init__(self) -> None:
        super().__init__("Keycloak M2M is disabled; cannot perform user operations.")


class UserNotFoundError(Exception):
    """Raised when a user cannot be found in Keycloak."""

    def __init__(self, user_id: str) -> None:
        super().__init__(f"User with id '{user_id}' was not found.")


class UserAlreadyExistsError(Exception):
    """Raised when a username or email already exists in Keycloak."""

    def __init__(self, username: str) -> None:
        super().__init__(f"User '{username}' already exists.")


class UserSummary(BaseModel):
    """Normalized user projection returned by Control Plane APIs."""

    id: str
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    email: str | None = None

    @classmethod
    def from_raw_user(cls, raw_user: dict[str, Any]) -> "UserSummary":
        """Build a user summary from a raw Keycloak user payload."""
        user_id = raw_user.get("id")
        if not user_id:
            raise ValueError("Cannot build UserSummary without an 'id'.")

        def _sanitize(value: object) -> str | None:
            if value is None:
                return None
            text = str(value).strip()
            return text or None

        return cls(
            id=user_id,
            first_name=_sanitize(raw_user.get("firstName")),
            last_name=_sanitize(raw_user.get("lastName")),
            username=_sanitize(raw_user.get("username")),
            email=_sanitize(raw_user.get("email")),
        )


class CreateUserRequest(BaseModel):
    """Minimal payload to create a user for temporary bootstrap workflows."""

    username: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    first_name: str | None = None
    last_name: str | None = None
    enabled: bool = True

    def to_keycloak_payload(self) -> dict[str, object]:
        """Return the Keycloak-compatible user payload."""
        return {
            "username": self.username,
            "email": self.email,
            "enabled": self.enabled,
            "firstName": self.first_name,
            "lastName": self.last_name,
            "credentials": [
                {
                    "type": "password",
                    "value": self.password,
                    "temporary": False,
                }
            ],
        }
