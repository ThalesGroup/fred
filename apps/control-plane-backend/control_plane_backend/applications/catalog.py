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

"""Validated reader for the build-generated Fred application catalog.

The ``ApplicationCatalogSource`` protocol is intentionally narrower than the
generated-file implementation. Durable installed/tombstoned registration can
later wrap this source without changing the discovery service or API contract.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from importlib import resources
from typing import Literal, Protocol

from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.capability.manifest import (
    APPLICATION_CAPABILITY_NAMESPACE_PREFIX,
    CAPABILITY_ID_PATTERN,
    TeamScopePolicy,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from control_plane_backend.applications.schemas import ApplicationList
from control_plane_backend.applications.schemas import (
    ApplicationSummary as ApplicationSummary,
)

_CATALOG_RESOURCE = "catalog.generated.json"
_APPLICATION_ID_PATTERN = r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
_SEMVER_PATTERN = (
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"
_ICON_PATTERN = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"
_CAPABILITY_ID_RE = re.compile(CAPABILITY_ID_PATTERN)


def _digest(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


class ApplicationCatalogItem(BaseModel):
    """One normalized row emitted by ``generate-applications.mjs``."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_APPLICATION_ID_PATTERN)
    capability_id: str = Field(min_length=1)
    kind: Literal["app"]
    version: str = Field(pattern=_SEMVER_PATTERN)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    # The build generator owns the Material Symbols allowlist. Revalidating
    # that list here would create a second source of truth which can reject a
    # valid generated catalog after the frontend adds a glyph. The package
    # boundary still rejects unsafe/non-ligature values independently.
    icon: str = Field(min_length=1, max_length=64, pattern=_ICON_PATTERN)
    host_api_version: Literal["1"]
    contract_digest: str = Field(pattern=_SHA256_PATTERN)
    service_required: bool
    admin_gated: Literal[True]

    @model_validator(mode="after")
    def _validate_derived_fields(self) -> "ApplicationCatalogItem":
        expected = f"{APPLICATION_CAPABILITY_NAMESPACE_PREFIX}{self.id}"
        if _CAPABILITY_ID_RE.fullmatch(self.capability_id) is None:
            raise ValueError(
                f"Application capability id {self.capability_id!r} does not "
                f"match {CAPABILITY_ID_PATTERN}."
            )
        if self.capability_id != expected:
            raise ValueError(
                f"Application {self.id!r} must use derived capability id "
                f"{expected!r}, not {self.capability_id!r}."
            )
        expected_name = f"applications.{self.id}.name"
        expected_description = f"applications.{self.id}.description"
        if self.name != expected_name or self.description != expected_description:
            raise ValueError(
                f"Application {self.id!r} must use deterministic i18n keys "
                f"{expected_name!r} and {expected_description!r}."
            )
        return self

    def capability_entry(self) -> CapabilityCatalogEntry:
        """Project the application into the shared admin entitlement catalog."""

        return CapabilityCatalogEntry(
            id=self.capability_id,
            version=self.version,
            name=self.name,
            description=self.description,
            icon=self.icon,
            kind="app",
            team_scope=TeamScopePolicy.ADMIN_GATED,
        )

    def summary(self) -> ApplicationSummary:
        """Drop installation/admin-only fields for a team-facing response."""

        return ApplicationSummary(
            id=self.id,
            version=self.version,
            name=self.name,
            description=self.description,
            icon=self.icon,
            host_api_version=self.host_api_version,
            contract_digest=self.contract_digest,
        )


class ApplicationCatalog(BaseModel):
    """Validated generated artifact shared by frontend and control-plane."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    catalog_revision: str = Field(pattern=_SHA256_PATTERN)
    items: list[ApplicationCatalogItem]

    @model_validator(mode="after")
    def _validate_unique_ids(self) -> "ApplicationCatalog":
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Generated application catalog contains duplicate ids.")
        capability_ids = [item.capability_id for item in self.items]
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError(
                "Generated application catalog contains duplicate capability ids."
            )
        if ids != sorted(ids):
            raise ValueError("Generated application catalog items must be id-sorted.")
        expected_revision = _digest(
            {
                "schema_version": self.schema_version,
                "items": [item.model_dump(mode="json") for item in self.items],
            }
        )
        if self.catalog_revision != expected_revision:
            raise ValueError(
                "Generated application catalog revision does not match its items."
            )
        return self

    def empty_list(self) -> ApplicationList:
        return ApplicationList(
            schema_version="1",
            catalog_revision=self.catalog_revision,
            items=[],
        )


class ApplicationCatalogSource(Protocol):
    """Source boundary for installed-application state."""

    def load(self) -> ApplicationCatalog: ...


class GeneratedApplicationCatalogSource:
    """Read the immutable catalog packaged into the control-plane wheel."""

    def load(self) -> ApplicationCatalog:
        return load_generated_application_catalog()


@lru_cache(maxsize=1)
def load_generated_application_catalog() -> ApplicationCatalog:
    catalog_resource = resources.files("control_plane_backend.applications").joinpath(
        _CATALOG_RESOURCE
    )
    return ApplicationCatalog.model_validate_json(catalog_resource.read_text("utf-8"))


GENERATED_APPLICATION_CATALOG_SOURCE = GeneratedApplicationCatalogSource()
