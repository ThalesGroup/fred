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

"""
The ONE capability registry (#1973, RFC AGENT-CAPABILITY-RFC.md §4).

Why this module exists:
- one registry replaces the five per-feature registration seams the RFC
  measures: it validates capabilities at pod boot (loudly), auto-discovers
  installed capability packages through the `fred.capabilities` entry point
  (installing the package IS the registration), and is the lookup surface
  agent assembly resolves selected capabilities against

How to use:
- pod boot: `registry = boot_capability_registry()` — discovers installed
  packages and fails startup with a named error on any invalid registration
- tests / in-tree capabilities: `registry.register(MyCapability())` then
  `registry.validate()`

Boot failures (each a named error, RFC §4):
- `DuplicateCapabilityIdError` — same id from two installed packages
- `DuplicateChatPartKindError` — ambiguous `UiPart` union discriminator
- `MissingRequiredEnvError` — declared env var absent at boot (§7.2)
- `DefaultOnRequiredSettingsError` — `default_on` + required team settings (§8.2)
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Mapping
from importlib.metadata import EntryPoint
from importlib.metadata import entry_points as _installed_entry_points
from typing import Any

from fred_sdk.contracts.capability import (
    AgentCapability,
    TeamScopePolicy,
    chat_part_kind,
)
from fred_sdk.contracts.ui_part_union import BASE_UI_PARTS, rebuild_ui_part_union
from pydantic import BaseModel

from .errors import (
    CapabilityRegistrationError,
    DefaultOnRequiredSettingsError,
    DuplicateCapabilityIdError,
    DuplicateChatPartKindError,
    MissingRequiredEnvError,
    UnknownCapabilityError,
)

logger = logging.getLogger(__name__)

FRED_CAPABILITIES_ENTRY_POINT_GROUP = "fred.capabilities"

# The frozen `UiPart` union members every pod already ships (RFC §3.6),
# derived from the SDK's one base list — never a second hand-kept enumeration.
BUILTIN_CHAT_PART_KINDS: frozenset[str] = frozenset(
    chat_part_kind(part) for part in BASE_UI_PARTS
)


def _as_capability(name: str, target: Any) -> AgentCapability[Any, Any, Any]:
    """Accept an `AgentCapability` subclass or instance; reject anything else."""

    if isinstance(target, type) and issubclass(target, AgentCapability):
        return target()
    if isinstance(target, AgentCapability):
        return target
    raise CapabilityRegistrationError(
        f"Entry point '{name}' in group '{FRED_CAPABILITIES_ENTRY_POINT_GROUP}' "
        f"must resolve to an AgentCapability subclass or instance, "
        f"got {target!r}."
    )


class CapabilityRegistry:
    """
    Registry of the capabilities installed on this pod.

    Lifecycle: `register()`/`discover()` at boot, then `validate()` once —
    any failure must abort pod startup. After boot the registry is read-only
    lookup for agent assembly (`fred_runtime.capabilities.assembly`).
    """

    def __init__(self) -> None:
        self._capabilities: dict[str, AgentCapability[Any, Any, Any]] = {}

    # -- registration -------------------------------------------------------

    def register(
        self,
        capability: AgentCapability[Any, Any, Any]
        | type[AgentCapability[Any, Any, Any]],
    ) -> str:
        """Register one capability; duplicate ids fail immediately (RFC §4)."""

        instance = _as_capability(
            getattr(capability, "__name__", str(capability)), capability
        )
        cap_id = instance.manifest.id
        existing = self._capabilities.get(cap_id)
        if existing is not None:
            raise DuplicateCapabilityIdError(
                f"Capability id '{cap_id}' is registered twice "
                f"(existing: {type(existing).__module__}.{type(existing).__name__}, "
                f"new: {type(instance).__module__}.{type(instance).__name__}). "
                "Capability ids must be unique across installed packages."
            )
        self._capabilities[cap_id] = instance
        return cap_id

    def discover(
        self, *, entry_points: Iterable[EntryPoint] | None = None
    ) -> list[str]:
        """
        Auto-discover installed capability packages (RFC §4, §7).

        Installing a package that declares a `fred.capabilities` entry point
        IS the registration — zero code edits in the pod. `entry_points`
        overrides the installed-package lookup (tests).
        """

        eps = (
            entry_points
            if entry_points is not None
            else _installed_entry_points(group=FRED_CAPABILITIES_ENTRY_POINT_GROUP)
        )
        registered: list[str] = []
        for ep in eps:
            try:
                target = ep.load()
            except Exception as exc:
                raise CapabilityRegistrationError(
                    f"Entry point '{ep.name}' "
                    f"({ep.value}) in group '{FRED_CAPABILITIES_ENTRY_POINT_GROUP}' "
                    f"failed to load: {exc}"
                ) from exc
            cap_id = self.register(_as_capability(ep.name, target))
            logger.info(
                "[CAPABILITY] discovered '%s' from entry point '%s' (%s)",
                cap_id,
                ep.name,
                ep.value,
            )
            registered.append(cap_id)
        return registered

    # -- boot validation -----------------------------------------------------

    def validate(self, env: Mapping[str, str] | None = None) -> None:
        """
        Boot validation (RFC §4) — call once after discovery; every failure
        raises a named `CapabilityRegistrationError` subclass so the pod
        fails startup loudly instead of degrading silently.
        """

        environment = os.environ if env is None else env
        self._validate_chat_part_kinds()
        self._validate_required_env(environment)
        self._validate_team_scope()
        # Registration contributes chat parts to the `UiPart` union at
        # model-build time (#1977, RFC §4): once the kinds are proven
        # unambiguous, fold them in so runtime events, tool results, and the
        # generated OpenAPI accept them with zero hand edits to union files.
        rebuild_ui_part_union(self.chat_parts())

    def _validate_chat_part_kinds(self) -> None:
        kind_owners: dict[str, str] = {
            kind: "fred-sdk builtin UiPart" for kind in BUILTIN_CHAT_PART_KINDS
        }
        for cap_id, capability in self._capabilities.items():
            for part in capability.manifest.chat_parts:
                kind = chat_part_kind(part)
                owner = kind_owners.get(kind)
                if owner is not None:
                    raise DuplicateChatPartKindError(
                        f"Chat-part kind '{kind}' declared by capability "
                        f"'{cap_id}' ({part.__name__}) is already contributed "
                        f"by {owner}. The UiPart union must stay unambiguous."
                    )
                kind_owners[kind] = f"capability '{cap_id}'"

    def _validate_required_env(self, env: Mapping[str, str]) -> None:
        for cap_id, capability in self._capabilities.items():
            missing = [
                var for var in capability.manifest.required_env if not env.get(var)
            ]
            if missing:
                raise MissingRequiredEnvError(
                    f"Capability '{cap_id}' requires environment variable(s) "
                    f"{', '.join(missing)} which are not set on this pod (RFC §7.2)."
                )

    def _validate_team_scope(self) -> None:
        for cap_id, capability in self._capabilities.items():
            if capability.manifest.team_scope is not TeamScopePolicy.DEFAULT_ON:
                continue
            required = [
                name
                for name, field in capability.TeamSettingsModel.model_fields.items()
                if field.is_required()
            ]
            if required:
                raise DefaultOnRequiredSettingsError(
                    f"Capability '{cap_id}' is team_scope=default_on but its "
                    f"TeamSettingsModel has required field(s) "
                    f"{', '.join(required)} (RFC §8.2). Default-on enablement "
                    "cannot depend on settings no team admin ever provided."
                )

    # -- lookup ---------------------------------------------------------------

    def capability(self, cap_id: str) -> AgentCapability[Any, Any, Any]:
        try:
            return self._capabilities[cap_id]
        except KeyError:
            raise UnknownCapabilityError(
                f"Capability '{cap_id}' is not installed on this pod. "
                f"Installed: {sorted(self._capabilities) or 'none'}."
            ) from None

    def ids(self) -> tuple[str, ...]:
        """All registered capability ids, sorted (the deterministic order, RFC §5.3)."""

        return tuple(sorted(self._capabilities))

    def chat_parts(self) -> tuple[type[BaseModel], ...]:
        """
        Every chat part contributed by the registered capabilities, in the
        deterministic capability order (sorted ids, manifest order within) —
        the exact extra set `rebuild_ui_part_union` folds into `UiPart` (#1977).
        """

        parts: dict[type[BaseModel], None] = {}
        for cap_id in self.ids():
            for part in self._capabilities[cap_id].manifest.chat_parts:
                parts[part] = None
        return tuple(parts)

    def __contains__(self, cap_id: object) -> bool:
        return cap_id in self._capabilities

    def __len__(self) -> int:
        return len(self._capabilities)

    # -- checkpointer allowlist (RFC §5.2 spike rule, #1971) ------------------

    def msgpack_allowlist(self) -> tuple[tuple[str, str], ...]:
        """
        Compose the typed-state opt-ins of every registered capability into
        `(module, name)` entries for `FredSqlCheckpointer`
        (`extra_msgpack_allowlist=`). JSON-primitive capability state needs no
        entry; the checkpointer keeps its own legacy entry regardless.
        """

        entries: list[tuple[str, str]] = []
        for cap_id in self.ids():
            for model in self._capabilities[cap_id].manifest.state_models:
                entries.append((model.__module__, model.__name__))
        return tuple(entries)


def boot_capability_registry(
    env: Mapping[str, str] | None = None,
    *,
    mcp_servers: Iterable[Any] | None = None,
) -> CapabilityRegistry:
    """
    Discover and validate the pod's capabilities — the one call pod startup
    makes. Any invalid registration raises a named error and MUST abort boot.

    `mcp_servers` are the loaded `mcp_catalog.yaml` entries (#1978, RFC §3.8,
    §6 Tier 1): each ENABLED server is registered as an `mcp:<server>`
    capability between entry-point discovery and boot validation, so a catalog
    id colliding with an installed capability still fails startup loudly.
    """

    from .mcp import register_mcp_capabilities

    registry = CapabilityRegistry()
    registry.discover()
    if mcp_servers is not None:
        register_mcp_capabilities(registry, mcp_servers)
    registry.validate(env)
    if len(registry):
        logger.info("[CAPABILITY] registry ready: %s", ", ".join(registry.ids()))
    return registry
