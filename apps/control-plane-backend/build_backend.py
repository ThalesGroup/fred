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

"""Setuptools backend that materializes the packaged application catalog."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from setuptools import build_meta as _setuptools_backend

_PROJECT_DIRECTORY = Path(__file__).resolve().parent
_REPOSITORY_DIRECTORY = _PROJECT_DIRECTORY.parent.parent
_CATALOG_PATH = (
    _PROJECT_DIRECTORY
    / "control_plane_backend"
    / "applications"
    / "catalog.generated.json"
)
_FRONTEND_DIRECTORY = _REPOSITORY_DIRECTORY / "apps" / "frontend"
_GENERATOR_PATH = _FRONTEND_DIRECTORY / "scripts" / "generate-applications.mjs"


def _validate_catalog() -> None:
    """Reject missing or stale catalogs before setuptools packages them.

    Call this after local generation or when building from an extracted source
    distribution whose catalog was generated before the archive was created.
    """

    try:
        catalog = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Packaged application catalog is unavailable: {_CATALOG_PATH}"
        ) from error

    if not isinstance(catalog, dict):
        raise RuntimeError("Packaged application catalog must be a JSON object")
    schema_version = catalog.get("schema_version")
    items = catalog.get("items")
    if schema_version != "1" or not isinstance(items, list):
        raise RuntimeError("Packaged application catalog has an invalid schema")

    canonical = json.dumps(
        {"schema_version": schema_version, "items": items},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    expected_revision = f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
    if catalog.get("catalog_revision") != expected_revision:
        raise RuntimeError("Packaged application catalog revision is invalid")


def _materialize_application_catalog() -> None:
    """Generate the catalog in a source checkout and validate the result.

    Artifact hooks call this before delegating to setuptools. Extracted source
    distributions have no monorepo generator, so they validate their embedded
    catalog instead.
    """

    if _GENERATOR_PATH.is_file():
        node = shutil.which("node")
        if node is None:
            raise RuntimeError(
                "Node.js is required to generate the Control Plane application catalog"
            )
        try:
            subprocess.run(  # nosec B603
                [node, str(_GENERATOR_PATH), "--control-plane-only"],
                cwd=_FRONTEND_DIRECTORY,
                check=True,
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                "Control Plane application catalog generation failed"
            ) from error

    _validate_catalog()


def build_wheel(
    wheel_directory: str,
    config_settings: dict[str, Any] | None = None,
    metadata_directory: str | None = None,
) -> str:
    """Build a wheel containing a freshly materialized application catalog.

    PEP 517 frontends call this hook with the standard setuptools arguments.
    """

    _materialize_application_catalog()
    return _setuptools_backend.build_wheel(
        wheel_directory,
        config_settings,
        metadata_directory,
    )


def build_sdist(
    sdist_directory: str,
    config_settings: dict[str, Any] | None = None,
) -> str:
    """Build a source distribution containing a validated application catalog.

    PEP 517 frontends call this hook with the standard setuptools arguments.
    """

    _materialize_application_catalog()
    return _setuptools_backend.build_sdist(sdist_directory, config_settings)


def build_editable(
    wheel_directory: str,
    config_settings: dict[str, Any] | None = None,
    metadata_directory: str | None = None,
) -> str:
    """Build an editable install after materializing its runtime catalog.

    Development installers call this PEP 660 hook with the standard setuptools
    arguments, ensuring an editable Control Plane never starts without a catalog.
    """

    _materialize_application_catalog()
    return _setuptools_backend.build_editable(
        wheel_directory,
        config_settings,
        metadata_directory,
    )


get_requires_for_build_wheel = _setuptools_backend.get_requires_for_build_wheel
get_requires_for_build_sdist = _setuptools_backend.get_requires_for_build_sdist
prepare_metadata_for_build_wheel = _setuptools_backend.prepare_metadata_for_build_wheel
get_requires_for_build_editable = _setuptools_backend.get_requires_for_build_editable
prepare_metadata_for_build_editable = (
    _setuptools_backend.prepare_metadata_for_build_editable
)
