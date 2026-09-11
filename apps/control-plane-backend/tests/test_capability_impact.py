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

import time
from types import SimpleNamespace

import pytest
from _rebac_test_doubles import CountingRebacEngine
from control_plane_backend.agent_instances.suspension import SuspensionReason
from control_plane_backend.capabilities import enablement as enablement_mod
from control_plane_backend.capabilities import impact as impact_mod
from control_plane_backend.capabilities import service as capability_service
from control_plane_backend.product.service import template_capability_id
from fred_core import (
    KeycloakUser,
    RebacDisabledResult,
    RebacReference,
    Relation,
    RelationType,
    Resource,
)
from test_main import _FakeAgentInstanceStore, _make_record


def _record_with(
    *,
    agent_instance_id: str,
    team_id: str,
    selected: list[str],
    suspension_reason: str | None = None,
    source_runtime_id: str = "runtime-a",
    source_agent_id: str = "rags.sample.echo",
):
    record = _make_record(
        agent_instance_id=agent_instance_id,
        team_id=team_id,
        source_runtime_id=source_runtime_id,
        source_agent_id=source_agent_id,
    )
    record.tuning = record.tuning.model_copy(
        update={"selected_capability_ids": selected}
    )
    record.suspension_reason = suspension_reason
    return record


class _NoOpRebac:
    """Stands in for `ReBAC` where the tuple fetch itself is stubbed out, so no
    lookup should ever reach the engine."""

    async def lookup_resources(self, *_args: object, **_kwargs: object) -> list:
        raise AssertionError("ListObjects must not be called by the impact module")


def _deps_with(store: _FakeAgentInstanceStore) -> SimpleNamespace:
    return SimpleNamespace(
        get_agent_instance_store=lambda: store,
        get_kpi_writer=lambda: None,
        team_dependencies=SimpleNamespace(rebac=_NoOpRebac()),
    )


def _team_subject(team_id: str) -> RebacReference:
    return RebacReference(type=Resource.TEAM, id=team_id)


def _cap_relation(
    subject: RebacReference, relation: RelationType, cap_id: str
) -> Relation:
    return Relation(
        subject=subject, relation=relation, resource=enablement_mod.cap_ref(cap_id)
    )


def _relations_for(usable_by_team: dict[str, set[str]], cap_id: str) -> list[Relation]:
    """Turn the test's "which teams may use this capability" intent into the
    capability's direct tuples, so the impact module folds `can_use` from the
    same tuple shape production reads."""

    return [
        _cap_relation(_team_subject(team_id), RelationType.ENABLED, cap_id)
        for team_id, usable in usable_by_team.items()
        if cap_id in usable
    ]


def _patch_pod_availability(
    monkeypatch: pytest.MonkeyPatch,
    available_by_source: dict[str, frozenset[str] | None],
) -> None:
    # `_available_capability_ids_by_source` is imported lazily from
    # product.service INSIDE the impact functions, so patch it at the source.
    from control_plane_backend.product import service as product_service

    async def _fake_available(_deps):
        return available_by_source

    monkeypatch.setattr(
        product_service, "_available_capability_ids_by_source", _fake_available
    )


def _patch_availability(
    monkeypatch: pytest.MonkeyPatch,
    *,
    available_by_source: dict[str, frozenset[str] | None],
    usable_by_team: dict[str, set[str]],
    rebac_disabled: bool = False,
) -> None:
    """Stub the two live-fact fetches the impact module makes."""

    _patch_pod_availability(monkeypatch, available_by_source)

    async def _fake_relations(_rebac, resource):
        if rebac_disabled:
            return RebacDisabledResult()
        return _relations_for(usable_by_team, resource.id)

    monkeypatch.setattr(impact_mod, "get_enablement_relations_cached", _fake_relations)


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
# Agent-template dependents (GitHub #2191) — an instance IS an instance of a
# kind="agent" template capability; that id is never in
# `selected_capability_ids`, so it was invisible to this module until now.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_impact_attributes_agent_template_capability_denied(
    monkeypatch,
) -> None:
    """An instance that selects NO tool capabilities still breaks when its OWN
    template capability is denied — previously invisible, since only
    `selected_capability_ids` was ever checked."""

    store = _FakeAgentInstanceStore(
        [
            _record_with(
                agent_instance_id="templated",
                team_id="team-a",
                selected=[],
                source_runtime_id="runtime-a",
                source_agent_id="rags.sample.echo",
            )
        ]
    )
    template_id = template_capability_id("runtime-a", "rags.sample.echo")
    _patch_availability(
        monkeypatch,
        available_by_source={"runtime-a": frozenset()},
        usable_by_team={"team-a": set()},  # template itself denied
    )

    result = await impact_mod.compute_capability_impact(_deps_with(store))

    assert result[template_id].suspended_instances == 1


@pytest.mark.asyncio
async def test_impact_gate_exempt_template_never_counted_broken(monkeypatch) -> None:
    """The internal self-test harness template is exempt from the CAPAB-01
    gate — it never carries a `can_use` tuple, so it must never be reported as
    broken just because its (never-granted) template id is absent from
    `usable_ids`."""

    store = _FakeAgentInstanceStore(
        [
            _record_with(
                agent_instance_id="harness",
                team_id="team-a",
                selected=[],
                source_agent_id="fred.github.self_test",
            )
        ]
    )
    _patch_availability(
        monkeypatch,
        available_by_source={"runtime-a": frozenset()},
        usable_by_team={"team-a": set()},
    )

    result = await impact_mod.compute_capability_impact(_deps_with(store))

    assert result == {}


@pytest.mark.asyncio
async def test_impact_unreachable_pod_skips_template_dependency_too(
    monkeypatch,
) -> None:
    """Unreachable pod ⇒ UNKNOWN for the template dependency too, same rule as
    a selected tool capability — never reported as broken on a transient
    outage."""

    store = _FakeAgentInstanceStore(
        [_record_with(agent_instance_id="templated", team_id="team-a", selected=[])]
    )
    template_id = template_capability_id("runtime-a", "rags.sample.echo")
    _patch_availability(
        monkeypatch,
        available_by_source={"runtime-a": None},
        usable_by_team={"team-a": set()},
    )

    result = await impact_mod.compute_capability_impact(_deps_with(store))

    assert result[template_id].suspended_instances == 0
    assert result[template_id].skipped_unreachable == 1


# ---------------------------------------------------------------------------
# The call budget: `can_use` is folded from each capability's own tuples, so
# the cost tracks the referenced capabilities, never the number of teams.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_impact_folds_can_use_without_one_listobjects_per_team(
    monkeypatch,
) -> None:
    """Five teams, two referenced capabilities: the verdicts must come from one
    tuple read per REFERENCED capability and no `ListObjects` at all, so the
    cost tracks the catalog rather than the user base."""

    org = enablement_mod.ORG_REF
    # `_for_all` is default-on but opted out for the whole personal class;
    # `_for_one` is granted to a single collaborative team.
    for_all = "fold_budget_for_all"
    for_one = "fold_budget_for_one"
    for cap_id in (for_all, for_one):
        enablement_mod.invalidate_capability_relations_cache(cap_id)

    personal_teams = [f"personal-u{index}" for index in range(3)]
    collaborative_teams = ["team-collab-0", "team-collab-1"]
    store = _FakeAgentInstanceStore(
        [
            _record_with(
                agent_instance_id=f"inst-{team_id}",
                team_id=team_id,
                selected=[for_all, for_one],
                # Gate-exempt template, so the only referenced ids are the two
                # tool capabilities above.
                source_agent_id="fred.github.self_test",
            )
            for team_id in personal_teams + collaborative_teams
        ]
    )
    rebac = CountingRebacEngine(
        direct_relations=[
            _cap_relation(org, RelationType.ORGANIZATION, for_all),
            _cap_relation(org, RelationType.DEFAULT_ON, for_all),
            _cap_relation(org, RelationType.PERSONAL_DISABLED, for_all),
            _cap_relation(org, RelationType.ORGANIZATION, for_one),
            _cap_relation(
                _team_subject("team-collab-0"), RelationType.ENABLED, for_one
            ),
        ]
    )
    _patch_pod_availability(monkeypatch, {"runtime-a": frozenset({for_all, for_one})})
    deps = SimpleNamespace(
        get_agent_instance_store=lambda: store,
        get_kpi_writer=lambda: None,
        team_dependencies=SimpleNamespace(rebac=rebac),
    )

    result = await impact_mod.compute_capability_impact(deps, collect_instances=True)

    # The personal class is opted out of the default-on capability; only
    # team-collab-0 holds the explicit grant on the other one.
    assert {item.team_id for item in result[for_all].instances} == set(personal_teams)
    assert {item.team_id for item in result[for_one].instances} == set(
        personal_teams + ["team-collab-1"]
    )
    # One read per referenced capability id, not one per team.
    read_ids = [resource.id for resource, _subject in rebac.list_direct_relations_calls]
    assert sorted(read_ids) == sorted([for_all, for_one])


@pytest.mark.asyncio
async def test_impact_skips_the_authorization_axis_when_rebac_is_disabled(
    monkeypatch,
) -> None:
    """ReBAC disabled means "no scoping": the fold reports `None` per team, the
    same signal `usable_capability_ids` used to return, so nothing is called
    broken on the authorization axis."""

    store = _FakeAgentInstanceStore(
        [_record_with(agent_instance_id="i", team_id="t", selected=["capa1"])]
    )
    _patch_availability(
        monkeypatch,
        available_by_source={"runtime-a": frozenset({"capa1"})},
        usable_by_team={},
        rebac_disabled=True,
    )

    result = await impact_mod.compute_capability_impact(_deps_with(store))

    assert result == {}


@pytest.mark.asyncio
async def test_impact_attributes_a_team_level_opt_out_of_a_default_on_capability(
    monkeypatch,
) -> None:
    """A `disabled` tuple revokes a default-on capability for that team alone -
    the tri-state the health column has to render, and the one branch a fold
    that only ever reads `enabled` would get wrong."""

    org = enablement_mod.ORG_REF
    cap_id = "fold_opt_out_capability"
    enablement_mod.invalidate_capability_relations_cache(cap_id)

    store = _FakeAgentInstanceStore(
        [
            _record_with(
                agent_instance_id=f"inst-{team_id}",
                team_id=team_id,
                selected=[cap_id],
                source_agent_id="fred.github.self_test",
            )
            for team_id in ("team-opted-out", "team-inherits", "personal-u0")
        ]
    )
    rebac = CountingRebacEngine(
        direct_relations=[
            _cap_relation(org, RelationType.ORGANIZATION, cap_id),
            _cap_relation(org, RelationType.DEFAULT_ON, cap_id),
            _cap_relation(
                _team_subject("team-opted-out"), RelationType.DISABLED, cap_id
            ),
        ]
    )
    _patch_pod_availability(monkeypatch, {"runtime-a": frozenset({cap_id})})
    deps = SimpleNamespace(
        get_agent_instance_store=lambda: store,
        get_kpi_writer=lambda: None,
        team_dependencies=SimpleNamespace(rebac=rebac),
    )

    result = await impact_mod.compute_capability_impact(deps, collect_instances=True)

    assert {item.team_id for item in result[cap_id].instances} == {"team-opted-out"}


@pytest.mark.asyncio
async def test_preview_revoke_reads_the_capability_fresh_not_the_cache(
    monkeypatch,
) -> None:
    """An admin confirms a mutation against this number, and only the writing
    replica invalidates the 45s cache. A stale entry saying "nobody is granted"
    must not make the dialog under-report."""

    org = enablement_mod.ORG_REF
    cap_id = "fold_preview_capability"
    store = _FakeAgentInstanceStore(
        [
            _record_with(
                agent_instance_id=f"inst-{index}",
                team_id=f"personal-u{index}",
                selected=[cap_id],
                source_agent_id="fred.github.self_test",
            )
            for index in range(3)
        ]
    )
    rebac = CountingRebacEngine(
        direct_relations=[
            _cap_relation(org, RelationType.ORGANIZATION, cap_id),
            _cap_relation(org, RelationType.PERSONAL_ON, cap_id),
        ]
    )
    # Another replica granted the class; this one still caches the pre-write
    # snapshot, under which every instance reads as already broken.
    enablement_mod._CAPABILITY_RELATIONS_CACHE.set(
        enablement_mod.cap_ref(cap_id), (time.time() + 60, [])
    )
    _patch_pod_availability(monkeypatch, {"runtime-a": frozenset({cap_id})})
    deps = SimpleNamespace(
        get_agent_instance_store=lambda: store,
        get_kpi_writer=lambda: None,
        team_dependencies=SimpleNamespace(rebac=rebac),
    )

    result = await impact_mod.preview_revoke_impact(
        deps, capability_id=cap_id, team_id=None
    )

    assert result.suspended_instances == 3
    # One fresh read of that capability; no ListObjects, no ListUsers.
    assert [
        resource.id for resource, _subject in rebac.list_direct_relations_calls
    ] == [cap_id]
    assert rebac.lookup_resources_calls == 0
    assert rebac.lookup_subjects_calls == 0


# ---------------------------------------------------------------------------
# Revoke preview — forward-looking, excludes the already-broken
# ---------------------------------------------------------------------------


def _preview_deps(
    monkeypatch: pytest.MonkeyPatch,
    store: _FakeAgentInstanceStore,
    relations: list[Relation],
    *,
    available_by_source: dict[str, frozenset[str] | None] | None = None,
) -> SimpleNamespace:
    """Deps for a revoke preview. It reads the capability's tuples fresh off
    the engine, so these tests state them literally instead of going through
    `_patch_availability`'s cached-fetch stub."""

    _patch_pod_availability(
        monkeypatch,
        available_by_source
        if available_by_source is not None
        else {"runtime-a": frozenset({"capa1"})},
    )
    return SimpleNamespace(
        get_agent_instance_store=lambda: store,
        get_kpi_writer=lambda: None,
        team_dependencies=SimpleNamespace(
            rebac=CountingRebacEngine(direct_relations=relations)
        ),
    )


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
    deps = _preview_deps(
        monkeypatch,
        store,
        [
            _cap_relation(enablement_mod.ORG_REF, RelationType.DEFAULT_ON, "capa1"),
            _cap_relation(_team_subject("team-gone"), RelationType.DISABLED, "capa1"),
        ],
    )

    result = await impact_mod.preview_revoke_impact(
        deps, capability_id="capa1", team_id=None
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
    deps = _preview_deps(
        monkeypatch,
        store,
        [
            _cap_relation(enablement_mod.ORG_REF, RelationType.DEFAULT_ON, "capa1"),
            _cap_relation(
                _team_subject("team-explicit"), RelationType.ENABLED, "capa1"
            ),
        ],
    )

    result = await impact_mod.preview_revoke_impact(
        deps, capability_id="capa1", team_id=None
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
    deps = _preview_deps(
        monkeypatch,
        store,
        [
            _cap_relation(
                _team_subject("team-explicit"), RelationType.ENABLED, "capa1"
            ),
        ],
    )

    result = await impact_mod.preview_revoke_impact(
        deps, capability_id="capa1", team_id="team-explicit"
    )

    assert result.suspended_instances == 1
    assert {i.agent_instance_id for i in result.instances} == {"explicit"}


@pytest.mark.asyncio
async def test_preview_revoke_includes_agent_template_instances(monkeypatch) -> None:
    """Previewing the revoke of a `kind="agent"` template capability must
    include instances that ARE that template — not just instances that
    selected it as a tool (GitHub #2191: before this fix, revoking a
    kind="agent" capability always previewed "0 agents affected" because the
    filter only ever checked `selected_capability_ids`, which never contains a
    template's own id)."""

    store = _FakeAgentInstanceStore(
        [
            _record_with(
                agent_instance_id="templated",
                team_id="team-a",
                selected=[],
                source_runtime_id="runtime-a",
                source_agent_id="rags.sample.echo",
            )
        ]
    )
    template_id = template_capability_id("runtime-a", "rags.sample.echo")
    deps = _preview_deps(
        monkeypatch,
        store,
        # Works today through the org-wide default, with no explicit grant to
        # exclude it from the platform-wide preview.
        [_cap_relation(enablement_mod.ORG_REF, RelationType.DEFAULT_ON, template_id)],
        available_by_source={"runtime-a": frozenset()},
    )

    result = await impact_mod.preview_revoke_impact(
        deps, capability_id=template_id, team_id=None
    )

    assert result.suspended_instances == 1
    assert {i.agent_instance_id for i in result.instances} == {"templated"}


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

    revived = await enablement_mod.revive_dependent_instances(
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

    revived = await enablement_mod.revive_dependent_instances(
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

    revived = await enablement_mod.revive_dependent_instances(
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

    revived = await enablement_mod.revive_dependent_instances(
        agent_instance_store=store,
        capability_id="capa1",
        usable_capability_ids={"capa1"},
        available_by_source={"runtime-a": None},  # pod unreachable
        team_id="team-a",
    )

    assert revived == 0
    assert record.suspension_reason == SuspensionReason.CAPABILITY_ACCESS_REVOKED.value


class _AdminRebac(_NoOpRebac):
    """Adds the org-admin gate and the structural anchor write the capability
    service performs before any read."""

    async def check_user_permission_or_raise(
        self, *_args: object, **_k: object
    ) -> None:
        return None

    async def add_relation(self, *_args: object, **_kwargs: object) -> None:
        return None


@pytest.mark.asyncio
async def test_revoke_preview_tolerates_a_model_the_catalog_dropped() -> None:
    """`disable_team_capability` keeps working for a model id a catalog fetch
    failed to re-advertise. The confirm dialog's preview runs behind the same
    gate on the same id, so it must tolerate the same absence."""

    deps = SimpleNamespace(
        configuration=SimpleNamespace(
            platform=SimpleNamespace(
                frontend=SimpleNamespace(
                    feature_flags=SimpleNamespace(enableApplications=False)
                ),
                application_sources=[],
                runtime_catalog_sources=[],
            )
        ),
        team_dependencies=SimpleNamespace(rebac=_AdminRebac()),
        get_agent_instance_store=lambda: _FakeAgentInstanceStore([]),
        get_kpi_writer=lambda: None,
    )

    preview = await capability_service.preview_capability_revoke(
        user=KeycloakUser(uid="admin", username="admin", roles=[], email=None),
        capability_id="model__openai__gpt-4o",
        team_id=None,
        deps=deps,
    )

    assert preview.capability_id == "model__openai__gpt-4o"
    assert preview.suspended_instances == 0
    assert preview.instances == []
