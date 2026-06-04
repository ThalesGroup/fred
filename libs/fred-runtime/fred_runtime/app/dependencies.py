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

"""FastAPI dependency helpers for pod container injection."""

from __future__ import annotations

from fastapi import FastAPI, Request

from fred_runtime.app.config import AgentPodConfig
from fred_runtime.app.context import PodApplicationContext

_CONTAINER_STATE_KEY = "pod_container"


def attach_pod_container(app: FastAPI, container: PodApplicationContext) -> None:
    """Store the container in app.state so routes can retrieve it via Depends."""
    setattr(app.state, _CONTAINER_STATE_KEY, container)


def get_pod_container_from_app(app: FastAPI) -> PodApplicationContext:
    """Return the container attached to a FastAPI app instance."""
    return getattr(app.state, _CONTAINER_STATE_KEY)  # type: ignore[no-any-return]


def get_pod_container(request: Request) -> PodApplicationContext:
    """FastAPI dependency: return the container for the current request's app."""
    return get_pod_container_from_app(request.app)


def get_pod_configuration(request: Request) -> AgentPodConfig:
    """FastAPI dependency: return the pod configuration from the container."""
    return get_pod_container(request).configuration
