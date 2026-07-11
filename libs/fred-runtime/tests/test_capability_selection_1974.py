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
Capability selection: stored-config envelope validation + lazy upgrade
(#1974, RFC AGENT-CAPABILITY-RFC.md §3.8, §3.9).

Covers the assembly-time half of capability selection:

- each persisted `capability_config` slice is the envelope
  `{"schema_version": ..., "config": {...}}`; assembly validates the inner
  config against the capability's `StoredConfigModel` when the version
  matches, and runs the optional lazy `upgrade_config` hook on mismatch —
  never a mass row migration
- invalid slices and failing upgrades raise the named
  `CapabilityConfigInvalidError` (the §3.9 `capability_config_invalid`
  suspension reason), never a silent degrade
- `build_capability_contexts` turns one agent's tuning-level selection
  (`selected_capability_ids` + `capability_config`) into the typed
  per-capability contexts the agent block consumes; unknown ids raise the
  existing `UnknownCapabilityError`
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityIdentity,
    CapabilityManifest,
    EmptyModel,
    StoredCapabilityConfig,
)
from fred_sdk.contracts.runtime import RuntimeServices
from pydantic import BaseModel

from fred_runtime.capabilities import (
    CapabilityRegistry,
    build_capability_agent_block,
    build_capability_contexts,
    resolve_stored_config,
)
from fred_runtime.capabilities.demo import DemoEchoCapability, DemoEchoConfig
from fred_runtime.capabilities.errors import (
    CapabilityConfigInvalidError,
    UnknownCapabilityError,
)

# ---------------------------------------------------------------------------
# Test capabilities
# ---------------------------------------------------------------------------


class GreeterConfigV2(BaseModel):
    """Current stored shape: v1's `salutation` was renamed to `greeting`."""

    greeting: str = "hello"
    loud: bool = False


class GreeterCapability(AgentCapability[GreeterConfigV2, GreeterConfigV2, EmptyModel]):
    """Capability with a real `upgrade_config` override (RFC §3.9)."""

    manifest = CapabilityManifest(
        id="greeter",
        version="2.0.0",
        name="capability.greeter.name",
        description="capability.greeter.description",
        icon="EmojiPeople",
    )
    ConfigModel = GreeterConfigV2

    def __init__(self) -> None:
        self.upgrade_calls: list[str] = []

    def upgrade_config(
        self, stored: Mapping[str, Any], from_version: str
    ) -> GreeterConfigV2:
        self.upgrade_calls.append(from_version)
        migrated = dict(stored)
        if "salutation" in migrated:
            migrated["greeting"] = migrated.pop("salutation")
        return GreeterConfigV2.model_validate(migrated)

    def middleware(
        self, ctx: CapabilityContext[GreeterConfigV2, EmptyModel]
    ) -> list[Any]:
        return []


def _identity() -> CapabilityIdentity:
    return CapabilityIdentity(user_id="alice")


def _registry(*capabilities: AgentCapability[Any, Any, Any]) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    for capability in capabilities:
        registry.register(capability)
    registry.validate(env={})
    return registry


# ---------------------------------------------------------------------------
# resolve_stored_config — envelope validation + lazy upgrade (RFC §3.9)
# ---------------------------------------------------------------------------


def test_current_version_slice_validates_without_upgrade() -> None:
    capability = GreeterCapability()
    config = resolve_stored_config(
        capability,
        {"schema_version": "2.0.0", "config": {"greeting": "bonjour", "loud": True}},
    )
    assert isinstance(config, GreeterConfigV2)
    assert config.greeting == "bonjour"
    assert config.loud is True
    assert capability.upgrade_calls == []


def test_version_mismatch_runs_upgrade_hook_lazily() -> None:
    capability = GreeterCapability()
    config = resolve_stored_config(
        capability,
        {"schema_version": "1.0.0", "config": {"salutation": "salut"}},
    )
    assert isinstance(config, GreeterConfigV2)
    assert config.greeting == "salut"
    assert capability.upgrade_calls == ["1.0.0"]


def test_default_upgrade_hook_validates_additive_old_shape() -> None:
    # DemoEchoCapability does not override upgrade_config: the default is
    # plain StoredConfigModel validation, correct for additive changes.
    config = resolve_stored_config(
        DemoEchoCapability(),
        {"schema_version": "0.0.1", "config": {"uppercase": True}},
    )
    assert isinstance(config, DemoEchoConfig)
    assert config.uppercase is True


def test_typed_envelope_input_is_accepted() -> None:
    config = resolve_stored_config(
        GreeterCapability(),
        StoredCapabilityConfig(schema_version="2.0.0", config={"greeting": "hi"}),
    )
    assert isinstance(config, GreeterConfigV2)
    assert config.greeting == "hi"


def test_invalid_slice_at_current_version_raises_named_error() -> None:
    with pytest.raises(CapabilityConfigInvalidError, match="greeter"):
        resolve_stored_config(
            GreeterCapability(),
            {"schema_version": "2.0.0", "config": {"loud": "not-a-bool"}},
        )


def test_failing_upgrade_raises_named_error() -> None:
    # v1 shape whose migrated form still does not validate.
    with pytest.raises(CapabilityConfigInvalidError, match="greeter"):
        resolve_stored_config(
            GreeterCapability(),
            {"schema_version": "1.0.0", "config": {"loud": "not-a-bool"}},
        )


def test_malformed_envelope_raises_named_error() -> None:
    with pytest.raises(CapabilityConfigInvalidError, match="greeter"):
        resolve_stored_config(GreeterCapability(), {"greeting": "no-envelope"})


# ---------------------------------------------------------------------------
# build_capability_contexts — tuning-level selection → typed contexts
# ---------------------------------------------------------------------------


def test_no_selection_yields_no_contexts() -> None:
    registry = _registry(DemoEchoCapability())
    for selected in (None, []):
        contexts = build_capability_contexts(
            registry,
            selected_capability_ids=selected,
            capability_config={},
            identity=_identity(),
            services=RuntimeServices(),
        )
        assert contexts == {}


def test_exact_selection_builds_typed_contexts() -> None:
    registry = _registry(DemoEchoCapability(), GreeterCapability())
    contexts = build_capability_contexts(
        registry,
        selected_capability_ids=["demo_echo", "greeter"],
        capability_config={
            "demo_echo": {"schema_version": "0.1.0", "config": {"uppercase": True}},
            "greeter": {"schema_version": "1.0.0", "config": {"salutation": "yo"}},
        },
        identity=_identity(),
        services=RuntimeServices(),
    )
    assert set(contexts) == {"demo_echo", "greeter"}
    demo_config = contexts["demo_echo"].config
    assert isinstance(demo_config, DemoEchoConfig)
    assert demo_config.uppercase is True
    greeter_config = contexts["greeter"].config
    assert isinstance(greeter_config, GreeterConfigV2)
    assert greeter_config.greeting == "yo"  # upgraded from the v1 shape


def test_selected_capability_without_slice_gets_model_defaults() -> None:
    registry = _registry(DemoEchoCapability())
    contexts = build_capability_contexts(
        registry,
        selected_capability_ids=["demo_echo"],
        capability_config={},
        identity=_identity(),
        services=RuntimeServices(),
    )
    config = contexts["demo_echo"].config
    assert isinstance(config, DemoEchoConfig)
    assert config.uppercase is False


def test_unknown_selected_capability_raises() -> None:
    registry = _registry(DemoEchoCapability())
    with pytest.raises(UnknownCapabilityError, match="not_installed"):
        build_capability_contexts(
            registry,
            selected_capability_ids=["not_installed"],
            capability_config={},
            identity=_identity(),
            services=RuntimeServices(),
        )


def test_contexts_feed_the_agent_block() -> None:
    registry = _registry(DemoEchoCapability())
    contexts = build_capability_contexts(
        registry,
        selected_capability_ids=["demo_echo"],
        capability_config={
            "demo_echo": {"schema_version": "0.1.0", "config": {"uppercase": True}}
        },
        identity=_identity(),
        services=RuntimeServices(),
    )
    block = build_capability_agent_block(registry, contexts)
    assert len(block.middleware) == 1
    tool_names = [tool.name for tool in block.middleware[0].tools]
    assert tool_names == ["demo_echo"]
