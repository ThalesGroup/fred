from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.app.container import ControlPlaneContainer
from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.config.models import Configuration


@dataclass(slots=True)
class UserServiceDependencies:
    """Bundle the collaborators required by user administration operations."""

    configuration: Configuration
    db: AsyncEngine


def build_user_service_dependencies(
    container: ControlPlaneContainer,
) -> UserServiceDependencies:
    return UserServiceDependencies(
        configuration=container.configuration,
        db=container.get_pg_async_engine(),
    )


def get_user_service_dependencies(request: Request) -> UserServiceDependencies:
    return build_user_service_dependencies(get_application_container(request))
