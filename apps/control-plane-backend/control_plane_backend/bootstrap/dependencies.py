# Copyright Thales 2026
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

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import Request
from fred_core import RebacEngine

from control_plane_backend.app.container import ControlPlaneContainer
from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.bootstrap.store import PlatformBootstrapStore
from control_plane_backend.config.models import Configuration


@dataclass(slots=True)
class BootstrapServiceDependencies:
    """
    Bundle the collaborators required by root platform-admin bootstrap (AUTHZ-07).

    Why this type exists:
    - the bootstrap endpoint needs the same explicit-dependency shape as
      `teams/` and `users/` — no hidden singleton lookups from business code

    How to use it:
    - build it from the application container in FastAPI dependencies
    - pass it to `control_plane_backend.bootstrap.service` functions

    Example:
    - `deps = build_bootstrap_service_dependencies(container)`
    """

    configuration: Configuration
    rebac: RebacEngine
    get_platform_bootstrap_store: Callable[[], PlatformBootstrapStore]


def build_bootstrap_service_dependencies(
    container: ControlPlaneContainer,
) -> BootstrapServiceDependencies:
    """
    Build explicit bootstrap-service collaborators from the application container.

    Why this function exists:
    - centralizes container wiring so `bootstrap/service.py` stays free of
      container lookups, matching the `teams/`/`users/` convention

    How to use it:
    - call from FastAPI dependencies for the bootstrap route

    Example:
    - `deps = build_bootstrap_service_dependencies(container)`
    """
    return BootstrapServiceDependencies(
        configuration=container.configuration,
        rebac=container.get_rebac_engine(),
        get_platform_bootstrap_store=container.get_platform_bootstrap_store,
    )


def get_bootstrap_service_dependencies(
    request: Request,
) -> BootstrapServiceDependencies:
    """
    Resolve request-scoped bootstrap-service collaborators from FastAPI state.

    Why this function exists:
    - the bootstrap route should consume explicit dependencies from the app
      container, same as every other route in this app

    How to use it:
    - declare it with `Depends(...)` in `bootstrap/api.py`

    Example:
    - `deps: BootstrapServiceDependencies = Depends(get_bootstrap_service_dependencies)`
    """
    return build_bootstrap_service_dependencies(get_application_container(request))
