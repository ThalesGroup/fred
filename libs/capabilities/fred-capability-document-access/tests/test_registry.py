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

"""Registry boot invariants for `document_access`.

`test_capability.py` hand-builds an `EntryPoint`; this reads the one the
INSTALLED distribution declares, so a typo in `pyproject.toml` fails here
rather than only at pod boot, and checks the stored config against the
runtime helpers that read it. fred-runtime is a dev-group (test-only)
dependency: discovery and `.validate()` are its concern.
"""

from __future__ import annotations

from importlib.metadata import distribution

from fred_runtime.capabilities import (
    CapabilityRegistry,
    evaluate_capability_chat_controls,
    resolve_bound_library_ids,
)
from fred_runtime.capabilities.registry import FRED_CAPABILITIES_ENTRY_POINT_GROUP
from fred_sdk.contracts.capability import AgentCapability
from fred_sdk.contracts.models import TeamScopePolicy

_CAPABILITY_ID = "document_access"
_FOLDER_ID = "00000000-0000-0000-0000-000000000201"


def _declared_entry_points():
    return [
        entry
        for entry in distribution("fred-capability-document-access").entry_points
        if entry.group == FRED_CAPABILITIES_ENTRY_POINT_GROUP
    ]


def test_installed_distribution_declares_the_capability() -> None:
    entries = _declared_entry_points()

    assert {entry.name for entry in entries} == {_CAPABILITY_ID}
    assert issubclass(entries[0].load(), AgentCapability)


def test_declared_entry_point_boots_into_a_registry() -> None:
    registry = CapabilityRegistry()

    registered = registry.discover(entry_points=_declared_entry_points())

    assert set(registered) == {_CAPABILITY_ID}
    # An empty env must not trip `_validate_required_env`: this capability
    # declares no required env var, so a bare pod boot must not fail.
    registry.validate(env={})


def test_capability_stays_default_on() -> None:
    # Unlike its siblings: baseline document access is deliberately not behind
    # a per-team admin gate, so installing this package makes it available.
    (entry,) = _declared_entry_points()

    assert entry.load().manifest.team_scope == TeamScopePolicy.DEFAULT_ON


def _registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.discover(entry_points=_declared_entry_points())
    return registry


def _envelope(config: dict[str, object]) -> dict[str, object]:
    version = _declared_entry_points()[0].load().manifest.version
    return {"schema_version": version, "config": config}


def test_stored_library_binding_reaches_the_server_side_ceiling() -> None:
    # The same stored slice drives the composer's pinned picker and the bound
    # scope fred-runtime enforces on `knowledge.search`.
    registry = _registry()
    stored = {
        _CAPABILITY_ID: _envelope(
            {"bind_libraries": True, "library_tag_ids": [_FOLDER_ID]}
        )
    }

    result = evaluate_capability_chat_controls(
        registry,
        capability_id=_CAPABILITY_ID,
        config_envelope=stored[_CAPABILITY_ID],
    )
    assert result.error is None
    scope = next(
        control for control in result.controls if control.widget == "document_scope"
    )
    assert scope.params is not None
    assert scope.params["bound_library_ids"] == [_FOLDER_ID]
    assert resolve_bound_library_ids(
        registry, capability_ids=[_CAPABILITY_ID], capability_config=stored
    ) == [_FOLDER_ID]


def test_inert_library_binding_sets_no_ceiling() -> None:
    registry = _registry()
    stored = {
        _CAPABILITY_ID: _envelope(
            {"bind_libraries": False, "library_tag_ids": [_FOLDER_ID]}
        )
    }
    result = evaluate_capability_chat_controls(
        registry,
        capability_id=_CAPABILITY_ID,
        config_envelope=stored[_CAPABILITY_ID],
    )
    assert result.error is None
    assert (
        resolve_bound_library_ids(
            registry, capability_ids=[_CAPABILITY_ID], capability_config=stored
        )
        is None
    )


def test_config_without_a_document_source_is_rejected() -> None:
    result = evaluate_capability_chat_controls(
        _registry(),
        capability_id=_CAPABILITY_ID,
        config_envelope=_envelope(
            {
                "bind_libraries": True,
                "library_tag_ids": [_FOLDER_ID],
                "team_documents": False,
            }
        ),
    )
    assert result.error is not None
    assert "needs at least one source" in result.error
    assert result.controls == []
