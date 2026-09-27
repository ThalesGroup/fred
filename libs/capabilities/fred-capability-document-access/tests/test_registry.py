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
rather than only at pod boot. fred-runtime is a dev-group (test-only)
dependency: discovery and `.validate()` are its concern.
"""

from __future__ import annotations

from importlib.metadata import distribution

from fred_runtime.capabilities import CapabilityRegistry
from fred_runtime.capabilities.registry import FRED_CAPABILITIES_ENTRY_POINT_GROUP
from fred_sdk.contracts.capability import AgentCapability
from fred_sdk.contracts.models import TeamScopePolicy

_CAPABILITY_ID = "document_access"


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
