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

"""Registry boot invariants for the five document capabilities.

Unlike the per-capability tests, which hand-build an `EntryPoint`, this reads
the entry points the INSTALLED distribution declares, so a typo in
`pyproject.toml` fails here rather than only at pod boot. fred-runtime is a
dev-group (test-only) dependency: discovery + `.validate()` are its concern.
"""

from __future__ import annotations

from importlib.metadata import distribution

from fred_runtime.capabilities import CapabilityRegistry
from fred_runtime.capabilities.registry import FRED_CAPABILITIES_ENTRY_POINT_GROUP
from fred_sdk.contracts.capability import AgentCapability
from fred_sdk.contracts.models import TeamScopePolicy

_EXPECTED_IDS = {
    "document_extract",
    "document_label_search",
    "document_similarity",
    "document_summarize",
    "document_verbatim",
}


def _declared_entry_points():
    return [
        entry
        for entry in distribution("fred-capability-documents").entry_points
        if entry.group == FRED_CAPABILITIES_ENTRY_POINT_GROUP
    ]


def test_installed_distribution_declares_the_five_capabilities() -> None:
    entries = _declared_entry_points()

    assert {entry.name for entry in entries} == _EXPECTED_IDS
    for entry in entries:
        assert issubclass(entry.load(), AgentCapability)


def test_declared_entry_points_boot_into_a_registry() -> None:
    registry = CapabilityRegistry()

    registered = registry.discover(entry_points=_declared_entry_points())

    assert set(registered) == _EXPECTED_IDS
    registry.validate(env={})


def test_every_capability_stays_admin_gated() -> None:
    # None of the five is DEFAULT_ON: a team admin opts an agent in explicitly,
    # so installing the package changes no existing agent's tool set.
    for entry in _declared_entry_points():
        assert entry.load().manifest.team_scope == TeamScopePolicy.ADMIN_GATED, (
            entry.name
        )
