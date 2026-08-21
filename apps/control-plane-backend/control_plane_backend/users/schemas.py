from __future__ import annotations

from enum import Enum
from typing import Any

from fred_core import RelationType
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


class PlatformAdminRootOnlyError(Exception):
    """Raised when a non-root caller tries to grant or revoke `platform_admin`.

    PLATFORM-ADMIN-DELEGATION-RFC.md §3: the `platform_admin` population is
    managed exclusively by the bootstrap root (`platformbootstrap.completed_by`)
    — appointed admins can neither appoint other admins nor revoke them.
    """

    def __init__(self) -> None:
        super().__init__("Only the bootstrap root can grant or revoke platform_admin.")


class PlatformRoleRootProtectedError(Exception):
    """Raised when a revocation targets the bootstrap root identity.

    PLATFORM-ADMIN-DELEGATION-RFC.md §3: the root is unrevocable for every
    caller, itself included — root self-demotion would be irreversible because
    bootstrap never reopens.
    """

    def __init__(self) -> None:
        super().__init__("The bootstrap root's platform_admin cannot be revoked.")


class PlatformBootstrapNotCompletedError(Exception):
    """Raised when platform_admin management is attempted before bootstrap ran.

    PLATFORM-ADMIN-DELEGATION-RFC.md §3: with no `platformbootstrap` row there
    is no root — `POST /bootstrap/platform-admin` is still open by definition
    (the marker is what closes it) and must be run first.
    """

    def __init__(self) -> None:
        super().__init__(
            "Root bootstrap has never run; run POST /bootstrap/platform-admin first."
        )


class PlatformRoleNotHeldError(Exception):
    """Raised when revoking a platform role the target user does not hold."""

    def __init__(self, user_id: str, relation: str) -> None:
        super().__init__(f"User '{user_id}' does not hold '{relation}'.")


class PlatformRolesRebacDisabledError(Exception):
    """Raised when platform-role management is attempted with ReBAC disabled.

    Mirrors `BootstrapRebacDisabledError`: with ReBAC disabled every write is
    a silent no-op (`NoopRebacEngine`) and every read is a
    `RebacDisabledResult`, so the surface must refuse instead of pretending.
    """

    def __init__(self) -> None:
        super().__init__("ReBAC is disabled; platform roles cannot be managed.")


class PlatformRoleRelation(str, Enum):
    """The two org-level relations the platform-roles surface manages.

    Deliberately narrower than `RelationType`: this surface must never write
    any other relation shape onto `organization:fred`.
    """

    PLATFORM_ADMIN = RelationType.PLATFORM_ADMIN.value
    PLATFORM_OBSERVER = RelationType.PLATFORM_OBSERVER.value

    def to_relation(self) -> RelationType:
        return RelationType(self.value)


class GrantPlatformRoleRequest(BaseModel):
    """Payload for `POST /users/{user_id}/platform-roles`."""

    relation: PlatformRoleRelation


class PlatformRoleHolder(BaseModel):
    """One user holding at least one platform role (RFC §3.1)."""

    user: "UserSummary"
    relations: list[PlatformRoleRelation]
    is_bootstrap_root: bool = False


class PlatformRolesResponse(BaseModel):
    """Response of `GET /users/platform-roles` (RFC §3.1).

    `caller_is_bootstrap_root` is a display convenience for the admin UI —
    the backend guards never rely on it.
    """

    holders: list[PlatformRoleHolder]
    caller_is_bootstrap_root: bool


class UserSummary(BaseModel):
    """Normalized user projection returned by Control Plane APIs."""

    id: str
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    email: str | None = None

    @classmethod
    def from_keycloak_user(cls, user: Any) -> "UserSummary":
        """
        Build a user summary from the authenticated Keycloak user object.

        Why this helper exists:
        - control-plane bootstrap endpoints already work with authenticated
          `KeycloakUser` values and should not rebuild user projections inline

        How to use it:
        - pass the current authenticated user dependency result

        Example:
        - `summary = UserSummary.from_keycloak_user(current_user)`
        """

        return cls(
            id=str(getattr(user, "uid")),
            username=getattr(user, "username", None),
        )

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
