from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UserNotFoundError(Exception):
    """Raised when a user cannot be found in the database."""

    def __init__(self, user_id: str) -> None:
        super().__init__(f"User with id '{user_id}' was not found.")


class UserAlreadyExistsError(Exception):
    """Raised when a username or email already exists."""

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
    def from_keycloak_user(cls, user: Any) -> "UserSummary":
        return cls(
            id=str(getattr(user, "uid")),
            username=getattr(user, "username", None),
            email=getattr(user, "email", None),
        )


class CreateUserRequest(BaseModel):
    """Payload to create a user."""

    username: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    first_name: str | None = None
    last_name: str | None = None
    enabled: bool = True
