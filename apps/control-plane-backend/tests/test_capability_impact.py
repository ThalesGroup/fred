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
Resting capability impact + the grant-side revive seam (CAPAB-01, #1975).

Covers the two things the health/impact work turns on:
- attribution is DERIVED, so an instance broken by capa1 must NOT count against
  capa2 even when it selects both (the exact miscount the stored
  `suspension_reason` cannot avoid);
- a GRANT revives the suspensions it resolves — the bug where re-enabling a
  capability left its agents suspended forever because only the never-scheduled
  reconciliation sweep could clear them.
"""

# pyright: reportArgumentType=false
# ^ these tests pass a lightweight SimpleNamespace/_FakeAgentInstanceStore fake
#   in place of ProductServiceDependencies/AgentInstanceStore, and a plain str
#   in place of TeamId, on purpose (same convention as
#   test_capability_selection_1974.py / test_capability_enablement_1980.py).
from __future__ import annotations

from types import SimpleNamespace

import pytest
from control_plane_backend.agent_instances.suspension import SuspensionReason
from control_plane_backend.capabilities import impact as impact_mod
from control_plane_backend.capabilities.enablement import revive_dependent_instances
from test_main import _FakeAgentInstanceStore, _make_record


def _record_with(
    *,
    agent_instance_id: str,
    team_id: str,
    selected: list[str],
    suspension_reason: str | None = None,
    source_runtime_id: str = "runtime-a",
):
    record = _make_record(
        agent_instance_id=agent_instance_id,
        team_id=team_id,
        source_runtime_id=source_runtime_id,
    )
    record.tuning = record.tuning.model_copy(
        update={"selected_capability_ids": selected}
    )
    record.suspension_reason = suspension_reason
    return record


class _NoOpRebac:
    """Stands in for `ReBAC` in tests that never exercise a real lookup — the
    platform-wide preview now reads `_explicitly_enabled_team_ids`, so a bare
    `object()` no longer suffices as the `rebac` stand-in."""

    async def lookup_subjects(self, *_args: object, **_kwargs: object) -> list:
        return []


def _deps_with(store: _FakeAgentInstanceStore) -> SimpleNamespace:
    return SimpleNamespace(
        get_agent_instance_store=lambda: store,
        get_kpi_writer=lambda: None,
        team_dependencies=SimpleNamespace(rebac=_NoOpRebac()),
    )


def _patch_availability(
    monkeypatch: pytest.MonkeyPatch,
    *,
    available_by_source: dict[str, frozenset[str] | None],
    usable_by_team: dict[str, set[str] | None],
) -> None:
    """Stub the two live-fact fetches the impact module makes."""

    async def _fake_available(_deps):
        return available_by_source

    async def _fake_usable(_rebac, team_id):
        return usable_by_team.get(str(team_id))

    # `_available_capability_ids_by_source` is imported lazily from
    # product.service INSIDE the impact functions, so patch it at the source.
    import control_plane_backend.product.service as product_service

    monkeypatch.setattr(
        product_service, "_available_capability_ids_by_source", _fake_available
    )
    monkeypatch.setattr(impact_mod, "usable_capability_ids", _fake_usable)


# ---------------------------------------------------------------------------
# Attribution — the multi-capability miscount the stored reason cannot avoid
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_impact_attributes_only_the_unusable_capability(monkeypatch) -> None:
    """An instance selecting capa1 + capa2 but denied only capa1 counts against
    capa1 ALONE — never capa2. This is the exact case a
    `suspension_reason IS NOT NULL AND capa2 IN selected` query gets wrong."""

    store = _FakeAgentInstanceStore(
        [
            _record_with(
                agent_instance_id="inst",
                team_id="team-a",
                selected=["capa1", "capa2"],
                suspension_reason=SuspensionReason.CAPABILITY_ACCESS_REVOKED.value,
            )
        ]
    )
    _patch_availability(
        monkeypatch,
        available_by_source={"runtime-a": frozenset({"capa1", "capa2"})},
        usable_by_team={"team-a": {"capa2"}},  # capa1 revoked, capa2 still usable
    )

    result = await impact_mod.compute_capability_impact(_deps_with(store))

    assert result["capa1"].suspended_instances == 1
    assert "capa2" not in result  # NOT miscounted against the healthy capability


@pytest.mark.asyncio
async def test_impact_collect_instances_names_broken_agents_by_team(
    monkeypatch,
) -> None:
    """`collect_instances=True` names each broken agent (id, team, display name)
    so the health-column drill-down can group by team — same derivation as the
    count, one entry per (instance, capability) it breaks."""

    store = _FakeAgentInstanceStore(
        [
            _record_with(
                agent_instance_id="inst-a",
                team_id="team-a",
                selected=["capa1"],
            ),
            _record_with(
                agent_instance_id="inst-b",
                team_id="team-b",
                selected=["capa1"],
            ),
        ]
    )
    _patch_availability(
        monkeypatch,
        available_by_source={"runtime-a": frozenset({"capa1"})},
        usable_by_team={"team-a": set(), "team-b": set()},  # capa1 revoked for both
    )

    result = await impact_mod.compute_capability_impact(
        _deps_with(store), collect_instances=True
    )

    assert result["capa1"].suspended_instances == 2
    by_team = {i.team_id: i.agent_instance_id for i in result["capa1"].instances}
    assert by_team == {"team-a": "inst-a", "team-b": "inst-b"}


@pytest.mark.asyncio
async def test_impact_counts_pod_missing_capability(monkeypatch) -> None:
    """A capability the pod no longer advertises breaks its selectors even when
    ReBAC still grants `can_use` — the `capability_unavailable` half."""

    store = _FakeAgentInstanceStore(
        [_record_with(agent_instance_id="i", team_id="t", selected=["gone"])]
    )
    _patch_availability(
        monkeypatch,
        available_by_source={"runtime-a": frozenset()},  # pod ships nothing
        usable_by_team={"t": {"gone"}},  # but ReBAC still allows it
    )

    result = await impact_mod.compute_capability_impact(_deps_with(store))

    assert result["gone"].suspended_instances == 1


@pytest.mark.asyncio
async def test_impact_reports_unreachable_pod_as_unknown_not_broken(
    monkeypatch,
) -> None:
    """An unreachable pod (None available set) is UNKNOWN, never broken — the
    sweep's `skipped_unreachable` rule, so a restart is not reported as an
    outage."""

    store = _FakeAgentInstanceStore(
        [_record_with(agent_instance_id="i", team_id="t", selected=["capa1"])]
    )
    _patch_availability(
        monkeypatch,
        available_by_source={"runtime-a": None},  # pod unreachable
        usable_by_team={"t": {"capa1"}},
    )

    result = await impact_mod.compute_capability_impact(_deps_with(store))

    assert result["capa1"].suspended_instances == 0
    assert result["capa1"].skipped_unreachable == 1


# ---------------------------------------------------------------------------
# Revoke preview — forward-looking, excludes the already-broken
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_excludes_already_broken_instances(monkeypatch) -> None:
    """ "This will suspend N agents" must mean agents that WORK today. An agent
    already broken by the capability is not newly suspended by revoking it."""

    # "works" lives in a team that currently HAS capa1; "already" lives in a
    # team that has already lost it (and is suspended for it). Revoking capa1
    # platform-wide breaks only the one that works today.
    store = _FakeAgentInstanceStore(
        [
            _record_with(
                agent_instance_id="works", team_id="team-ok", selected=["capa1"]
            ),
            _record_with(
                agent_instance_id="already",
                team_id="team-gone",
                selected=["capa1"],
                suspension_reason=SuspensionReason.CAPABILITY_ACCESS_REVOKED.value,
            ),
        ]
    )
    _patch_availability(
        monkeypatch,
        available_by_source={"runtime-a": frozenset({"capa1"})},
        usable_by_team={
            "team-ok": {"capa1"},  # works today → revoke would break it
            "team-gone": set(),  # already lost capa1 → already broken
        },
    )

    result = await impact_mod.preview_revoke_impact(
        _deps_with(store), capability_id="capa1", team_id=None
    )

    assert result.suspended_instances == 1
    assert {i.agent_instance_id for i in result.instances} == {"works"}


@pytest.mark.asyncio
async def test_preview_default_off_excludes_explicitly_enabled_teams(
    monkeypatch,
) -> None:
    """`set_capability_default_on(False)` skips teams that already carry an
    explicit `enabled` grant — they keep `can_use` by their own tuple, not by
    inheritance, so the mutation never touches them. The platform-wide preview
    (`team_id=None`) must agree, or the confirmation dialog overstates impact
    by counting an agent that will not actually be suspended. This fails on the
    old behavior, which counted every team that currently works."""

    store = _FakeAgentInstanceStore(
        [
            _record_with(
                agent_instance_id="inherits",
                team_id="team-inherits",
                selected=["capa1"],
            ),
            _record_with(
                agent_instance_id="explicit",
                team_id="team-explicit",
                selected=["capa1"],
            ),
        ]
    )
    _patch_availability(
        monkeypatch,
        available_by_source={"runtime-a": frozenset({"capa1"})},
        usable_by_team={
            "team-inherits": {"capa1"},
            "team-explicit": {"capa1"},
        },
    )

    async def _fake_explicitly_enabled(_rebac, _capability_id):
        return {"team-explicit"}

    import control_plane_backend.capabilities.enablement as enablement_mod

    monkeypatch.setattr(
        enablement_mod, "_explicitly_enabled_team_ids", _fake_explicitly_enabled
    )

    result = await impact_mod.preview_revoke_impact(
        _deps_with(store), capability_id="capa1", team_id=None
    )

    assert result.suspended_instances == 1
    assert {i.agent_instance_id for i in result.instances} == {"inherits"}


@pytest.mark.asyncio
async def test_preview_single_team_disable_ignores_explicit_enabled_exclusion(
    monkeypatch,
) -> None:
    """A single-team preview (`team_id` given) previews an explicit disable for
    THAT team alone — the explicit-enabled exclusion is a platform-wide-preview
    concept only and must not suppress this team's own impact."""

    store = _FakeAgentInstanceStore(
        [
            _record_with(
                agent_instance_id="explicit",
                team_id="team-explicit",
                selected=["capa1"],
            ),
        ]
    )
    _patch_availability(
        monkeypatch,
        available_by_source={"runtime-a": frozenset({"capa1"})},
        usable_by_team={"team-explicit": {"capa1"}},
    )

    async def _fake_explicitly_enabled(_rebac, _capability_id):
        return {"team-explicit"}

    import control_plane_backend.capabilities.enablement as enablement_mod

    monkeypatch.setattr(
        enablement_mod, "_explicitly_enabled_team_ids", _fake_explicitly_enabled
    )

    result = await impact_mod.preview_revoke_impact(
        _deps_with(store), capability_id="capa1", team_id="team-explicit"
    )

    assert result.suspended_instances == 1
    assert {i.agent_instance_id for i in result.instances} == {"explicit"}


# ---------------------------------------------------------------------------
# The revive fix — the grant-side seam that was missing entirely
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revive_clears_suspension_when_all_capabilities_return() -> None:
    """A grant that makes EVERY selected capability usable clears the
    suspension — the re-enable path that previously left agents stranded."""

    record = _record_with(
        agent_instance_id="inst",
        team_id="team-a",
        selected=["capa1"],
        suspension_reason=SuspensionReason.CAPABILITY_ACCESS_REVOKED.value,
    )
    store = _FakeAgentInstanceStore([record])

    revived = await revive_dependent_instances(
        agent_instance_store=store,
        capability_id="capa1",
        usable_capability_ids={"capa1"},
        available_by_source={"runtime-a": frozenset({"capa1"})},
        team_id="team-a",
    )

    assert revived == 1
    assert record.suspension_reason is None


@pytest.mark.asyncio
async def test_revive_keeps_suspension_when_another_capability_still_missing() -> None:
    """Re-enabling capa1 must NOT revive an instance still broken by capa2 — the
    reason a grant cannot fake `selected - {id}` like the revoke path does."""

    record = _record_with(
        agent_instance_id="inst",
        team_id="team-a",
        selected=["capa1", "capa2"],
        suspension_reason=SuspensionReason.CAPABILITY_ACCESS_REVOKED.value,
    )
    store = _FakeAgentInstanceStore([record])

    revived = await revive_dependent_instances(
        agent_instance_store=store,
        capability_id="capa1",
        usable_capability_ids={"capa1"},  # capa2 still NOT usable
        available_by_source={"runtime-a": frozenset({"capa1", "capa2"})},
        team_id="team-a",
    )

    assert revived == 0
    assert record.suspension_reason == SuspensionReason.CAPABILITY_ACCESS_REVOKED.value


@pytest.mark.asyncio
async def test_revive_never_touches_config_invalid_suspension() -> None:
    """A `capability_config_invalid` suspension is cleared only by a successful
    save (RFC §3.9) — a grant must leave it alone even when access returns."""

    record = _record_with(
        agent_instance_id="inst",
        team_id="team-a",
        selected=["capa1"],
        suspension_reason=SuspensionReason.CAPABILITY_CONFIG_INVALID.value,
    )
    store = _FakeAgentInstanceStore([record])

    revived = await revive_dependent_instances(
        agent_instance_store=store,
        capability_id="capa1",
        usable_capability_ids={"capa1"},
        available_by_source={"runtime-a": frozenset({"capa1"})},
        team_id="team-a",
    )

    assert revived == 0
    assert record.suspension_reason == SuspensionReason.CAPABILITY_CONFIG_INVALID.value


@pytest.mark.asyncio
async def test_revive_skips_unreachable_pod() -> None:
    """An unreachable pod means UNKNOWN — a grant must not clear a suspension it
    cannot prove is resolved."""

    record = _record_with(
        agent_instance_id="inst",
        team_id="team-a",
        selected=["capa1"],
        suspension_reason=SuspensionReason.CAPABILITY_ACCESS_REVOKED.value,
    )
    store = _FakeAgentInstanceStore([record])

    revived = await revive_dependent_instances(
        agent_instance_store=store,
        capability_id="capa1",
        usable_capability_ids={"capa1"},
        available_by_source={"runtime-a": None},  # pod unreachable
        team_id="team-a",
    )

    assert revived == 0
    assert record.suspension_reason == SuspensionReason.CAPABILITY_ACCESS_REVOKED.value
