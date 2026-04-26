from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import Request
from fred_core import KeycloackDisabled, create_keycloak_admin
from keycloak import KeycloakAdmin

from control_plane_backend.app.container import ControlPlaneContainer
from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.config.models import Configuration

KeycloakAdminFactory = Callable[[], KeycloakAdmin | KeycloackDisabled]


@dataclass(slots=True)
class UserServiceDependencies:
    """
    Bundle the collaborators required by user administration operations.

    Why this type exists:
    - Slice 4 moves `users/` away from hidden singleton lookups and toward
      explicit dependency injection
    - grouping the collaborators keeps route handlers small while making the
      user-service contract visible and testable

    How to use it:
    - build it from the application container in FastAPI dependencies
    - pass it to `control_plane_backend.users.service` functions

    Example:
    - `deps = build_user_service_dependencies(container)`
    """

    configuration: Configuration
    create_keycloak_admin_client: KeycloakAdminFactory


def build_user_service_dependencies(
    container: ControlPlaneContainer,
) -> UserServiceDependencies:
    """
    Build explicit user-service collaborators from the application container.

    Why this function exists:
    - user administration still depends on security configuration and Keycloak
      client construction
    - centralizing that wiring keeps service code free of container lookups

    How to use it:
    - call from FastAPI dependencies for request-scoped user routes
    - reuse it from compatibility bridges until the global context shim is gone

    Example:
    - `deps = build_user_service_dependencies(container)`
    """
    return UserServiceDependencies(
        configuration=container.configuration,
        create_keycloak_admin_client=lambda: create_keycloak_admin(
            container.configuration.security.m2m
        ),
    )


def get_user_service_dependencies(request: Request) -> UserServiceDependencies:
    """
    Resolve request-scoped user-service collaborators from FastAPI state.

    Why this function exists:
    - user routes should consume explicit dependencies from the app container
      instead of relying on hidden globals in business code

    How to use it:
    - declare it with `Depends(...)` in user route handlers
    - pass the returned bundle to user service functions

    Example:
    - `deps: UserServiceDependencies = Depends(get_user_service_dependencies)`
    """
    return build_user_service_dependencies(get_application_container(request))
