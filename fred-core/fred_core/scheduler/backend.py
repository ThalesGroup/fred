# Copyright Thales 2025
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

from enum import StrEnum


class SchedulerBackend(StrEnum):
    """
    Allowed scheduler backend values across Fred backends.

    Why this exists:
    - Avoid raw string literals (`"temporal"`, `"memory"`) spread in business code.
    - Keep one typed source of truth used by configuration parsing and runtime checks.

    How to use:
    ```python
    from fred_core.scheduler import SchedulerBackend

    if backend == SchedulerBackend.MEMORY:
        ...
    ```
    """

    TEMPORAL = "temporal"
    MEMORY = "memory"


def resolve_scheduler_backend(
    configured_backend: str | SchedulerBackend,
) -> SchedulerBackend:
    """
    Return the effective scheduler backend after standalone override.

    Why this exists:
    - YAML may keep `backend: temporal` for production parity.
    - In standalone mode we still need in-memory scheduling without editing YAML.

    How to use:
    ```python
    from fred_core.scheduler import resolve_scheduler_backend

    backend = resolve_scheduler_backend(configuration.scheduler.backend)
    if backend == SchedulerBackend.MEMORY:
        ...
    ```
    """
    if isinstance(configured_backend, SchedulerBackend):
        backend = configured_backend
    else:
        normalized = configured_backend.strip().lower()
        try:
            backend = SchedulerBackend(normalized)
        except ValueError as exc:
            raise ValueError(
                f"Unsupported scheduler backend '{configured_backend}'. Expected 'temporal' or 'memory'."
            ) from exc

    return backend
