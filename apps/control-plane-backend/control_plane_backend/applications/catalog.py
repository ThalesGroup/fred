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

"""Registration of the applications a Fred deployment serves.

An application ships as its own UI service (and optionally its own API);
Fred never compiles application code, so registration is deployment
configuration rather than a build artifact. The ``ApplicationCatalogSource``
protocol keeps discovery independent of where that registration comes from,
so durable installed/tombstoned state can later replace the configured source
without changing the discovery service or the API contract.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from fred_core.security.rebac.capability_authz import (
    application_capability_id,
)
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.capability.manifest import (
    CAPABILITY_ID_PATTERN,
    TeamScopePolicy,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from control_plane_backend.applications.schemas import ApplicationSummary

APPLICATION_ID_PATTERN = r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
# Mirrors RESERVED_IDS in apps/frontend/scripts/application-proxy.mjs: these
# collide with nginx map directives the gateway generates from the same
# config, so a control-plane-accepted id the gateway then rejects would grant
# a capability for an application whose frontend container fails to start.
# Keep the two lists identical.
_RESERVED_APPLICATION_IDS = frozenset({"default", "hostnames", "include", "volatile"})
_SEMVER_PATTERN = (
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_ICON_PATTERN = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"
_CAPABILITY_ID_RE = re.compile(CAPABILITY_ID_PATTERN)
_LOCALE_RE = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
# Characters that would break out of an href/src attribute or an nginx
# directive if an operator pasted a hostile value into deployment config.
_UNSAFE_URL_RE = re.compile(r"""[\s"'\\<>`{}|^]""")
_TRAVERSAL_RE = re.compile(r"(?:^|/)\.{1,2}(?:/|$)")
_MAX_DISPLAY_TEXT = 200
# Own-origin route root. The gateway keys its upstream map on the path segment
# after this prefix, so a same-origin ui_prefix has exactly one routable value.
_UI_ROUTE_ROOT = "/apps"


def _reject_unsafe(value: str, field: str) -> None:
    if _UNSAFE_URL_RE.search(value):
        raise ValueError(f"{field} must not contain whitespace or quoting characters")
    if _TRAVERSAL_RE.search(value):
        raise ValueError(f"{field} must not contain path traversal")


def _normalized_ui_prefix(value: str) -> str:
    """Shape and safety only; the root-relative form is pinned to the app id
    by ``_validate_registration``, which is where the id is known.

    Moving an application to its own origin must stay a config edit, so the
    absolute form stays free-form.
    """

    _reject_unsafe(value, "ui_prefix")
    if value.startswith("//"):
        raise ValueError("ui_prefix must not be protocol-relative")
    parsed = urlsplit(value)
    if parsed.query or parsed.fragment:
        raise ValueError("ui_prefix must not carry a query or a fragment")
    if value.startswith("/"):
        return value.rstrip("/") or "/"
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(
            "ui_prefix must be a root-relative path or an absolute http(s) URL"
        )
    if parsed.username or parsed.password:
        raise ValueError("ui_prefix must not carry credentials")
    try:
        parsed.port
    except ValueError as exc:
        # A non-numeric or out-of-range (0-65535) port passes urlsplit() itself
        # — it only raises when the port is actually read. The browser's own
        # `new URL()` rejects the same value, so left unchecked here this
        # would authorize an application that can never render.
        raise ValueError(f"ui_prefix has an invalid port: {exc}") from exc
    return value.rstrip("/")


def _validated_localized_text(value: dict[str, str], field: str) -> dict[str, str]:
    if "en" not in value:
        raise ValueError(f"{field} must provide an 'en' entry, used as the fallback")
    for locale, text in value.items():
        if _LOCALE_RE.fullmatch(locale) is None:
            raise ValueError(f"{field} key {locale!r} is not a language tag")
        if not text.strip() or len(text) > _MAX_DISPLAY_TEXT:
            raise ValueError(
                f"{field} text for {locale!r} must be 1 to "
                f"{_MAX_DISPLAY_TEXT} characters"
            )
    return value


class ApplicationSourceConfig(BaseModel):
    """One application this deployment serves, registered by an operator.

    Mirrors ``RuntimeCatalogSourceConfig``. Everything here is browser-facing
    or catalog metadata: the server-side proxy upstreams belong to the
    frontend gateway, which is the only process that routes to them.
    """

    model_config = ConfigDict(extra="forbid")

    app_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=APPLICATION_ID_PATTERN,
        description=(
            "Application id. Interpolated into /apps/<app_id>/ and "
            "/app-services/<app_id>/, and into the app__<app_id> capability "
            "the team authorization grant is written against."
        ),
    )
    ui_prefix: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description=(
            "Browser-facing prefix the application frame loads. Must be "
            "exactly /apps/<app_id> while the UI is served from Fred's "
            "origin, or an absolute http(s) URL when it is served from its "
            "own."
        ),
    )
    version: str = Field(..., pattern=_SEMVER_PATTERN)
    # This model is the only validator of the value now: it is rendered as a
    # Material Symbols ligature, so the pattern is the whole safety boundary.
    icon: str = Field(default="extension", max_length=64, pattern=_ICON_PATTERN)
    display_name: dict[str, str] = Field(
        ..., description='Locale to display name, e.g. {"en": "Reactor"}.'
    )
    description: dict[str, str] = Field(..., description="Locale to description.")
    enabled: bool = True

    @field_validator("app_id")
    @classmethod
    def _check_app_id(cls, value: str) -> str:
        if value in _RESERVED_APPLICATION_IDS:
            raise ValueError(
                f"app_id {value!r} is reserved by the frontend gateway "
                f"({sorted(_RESERVED_APPLICATION_IDS)}) and cannot be registered"
            )
        return value

    @field_validator("ui_prefix")
    @classmethod
    def _check_ui_prefix(cls, value: str) -> str:
        return _normalized_ui_prefix(value)

    @field_validator("display_name", "description")
    @classmethod
    def _check_localized_text(
        cls, value: dict[str, str], info: ValidationInfo
    ) -> dict[str, str]:
        return _validated_localized_text(value, info.field_name or "localized text")

    @model_validator(mode="after")
    def _validate_registration(self) -> "ApplicationSourceConfig":
        if _CAPABILITY_ID_RE.fullmatch(self.capability_id) is None:
            raise ValueError(
                f"Application {self.app_id!r} derives capability id "
                f"{self.capability_id!r}, which does not match "
                f"{CAPABILITY_ID_PATTERN}."
            )
        own_origin_route = f"{_UI_ROUTE_ROOT}/{self.app_id}"
        if self.ui_prefix.startswith("/") and self.ui_prefix != own_origin_route:
            raise ValueError(
                f"Application {self.app_id!r} must use ui_prefix "
                f"{own_origin_route!r} while its UI is served from Fred's "
                f"origin, not {self.ui_prefix!r}: the gateway routes on the "
                "path segment after /apps/, so any other path 404s. Give it "
                "an absolute http(s) URL to serve the UI from its own origin."
            )
        return self

    @property
    def capability_id(self) -> str:
        """Derived, never authored: team admission filters on exactly this id."""

        return application_capability_id(self.app_id)

    def capability_entry(self) -> CapabilityCatalogEntry:
        """Project the application into the shared admin entitlement catalog.

        That catalog carries single-string labels, so the mandatory "en" entry
        is the one that travels; the browser-facing surface keeps every locale.
        """

        return CapabilityCatalogEntry(
            id=self.capability_id,
            version=self.version,
            name=self.display_name["en"],
            description=self.description["en"],
            icon=self.icon,
            kind="app",
            team_scope=TeamScopePolicy.ADMIN_GATED,
        )

    def summary(self) -> ApplicationSummary:
        """Drop registration-only fields for a team-facing response."""

        return ApplicationSummary(
            id=self.app_id,
            version=self.version,
            name=self.display_name,
            description=self.description,
            icon=self.icon,
            ui_prefix=self.ui_prefix,
        )


class ApplicationCatalog(BaseModel):
    """Applications registered and currently serving in this deployment."""

    model_config = ConfigDict(extra="forbid")

    items: list[ApplicationSourceConfig]


class ApplicationCatalogSource(Protocol):
    """Source boundary for registered-application state."""

    def load(self) -> ApplicationCatalog: ...


def registered_applications(
    sources: Sequence[ApplicationSourceConfig],
) -> list[ApplicationSourceConfig]:
    """Enabled entries only: `enabled: false` parks an app without deleting it."""

    return [source for source in sources if source.enabled]


@dataclass(frozen=True)
class ConfiguredApplicationCatalogSource:
    """Read the applications an operator registered in platform configuration."""

    sources: tuple[ApplicationSourceConfig, ...] = ()

    def load(self) -> ApplicationCatalog:
        return ApplicationCatalog(items=registered_applications(self.sources))
