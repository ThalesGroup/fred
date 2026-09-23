"""Control-plane startup of account standing (`main._initialize_account_standing`).

Every person is in good standing unless Fred banned them: each start writes the
everyone entry and the ready marker, reads the marker back, and refuses to start
when any step fails. The lifespan runs this step before the startup reconciliations.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from _standing_test_doubles import (
    EVERYONE_ACTIVE,
    STANDING_READY,
    StandingRebacEngine,
    ban,
)
from control_plane_backend import main
from fred_core import StandingAuthorizationError

_STARTUP_CALLS = [
    "validate_standing_model",
    "grant_default_standing",
    "mark_standing_seed_ready",
    "is_standing_seed_ready",
]


class _MarkerLandsNowhere(StandingRebacEngine):
    """A marker write that the store acknowledges but never keeps."""

    async def mark_standing_seed_ready(self) -> str | None:
        self.calls.append("mark_standing_seed_ready")
        return self.HIGHER_CONSISTENCY


def _container(rebac: StandingRebacEngine) -> SimpleNamespace:
    return SimpleNamespace(get_rebac_engine=lambda: rebac)


@pytest.mark.asyncio
async def test_startup_puts_every_person_in_good_standing_then_confirms_the_marker() -> (
    None
):
    rebac = StandingRebacEngine()

    await main._initialize_account_standing(_container(rebac))

    assert rebac.calls == _STARTUP_CALLS
    assert rebac.relations == {EVERYONE_ACTIVE, STANDING_READY}
    # A person with no tuple of their own passes the real standing check.
    await rebac.require_user_standing("synthetic-person")


@pytest.mark.asyncio
async def test_starts_over_a_stored_ban_keeps_that_person_refused() -> None:
    rebac = StandingRebacEngine(relations={ban("synthetic-banned-person")})

    await main._initialize_account_standing(_container(rebac))
    await main._initialize_account_standing(_container(rebac))

    assert rebac.relations == {
        EVERYONE_ACTIVE,
        STANDING_READY,
        ban("synthetic-banned-person"),
    }
    with pytest.raises(StandingAuthorizationError):
        await rebac.require_user_standing("synthetic-banned-person")
    await rebac.require_user_standing("synthetic-person")


@pytest.mark.asyncio
async def test_startup_makes_no_standing_call_while_standing_is_not_enforced() -> None:
    rebac = StandingRebacEngine(enforces_standing=False)

    await main._initialize_account_standing(_container(rebac))

    assert rebac.calls == []
    assert rebac.relations == set()


@pytest.mark.asyncio
async def test_model_validation_failure_refuses_startup_and_writes_nothing() -> None:
    class _UnsupportedModel(StandingRebacEngine):
        async def validate_standing_model(self) -> None:
            await super().validate_standing_model()
            raise RuntimeError("Standing authorization model is not available.")

    rebac = _UnsupportedModel()

    with pytest.raises(RuntimeError, match="model is not available"):
        await main._initialize_account_standing(_container(rebac))

    assert rebac.calls == ["validate_standing_model"]
    assert rebac.relations == set()


@pytest.mark.asyncio
async def test_default_standing_failure_refuses_startup_before_the_marker() -> None:
    class _UnreachableStore(StandingRebacEngine):
        async def grant_default_standing(self) -> str | None:
            self.calls.append("grant_default_standing")
            raise RuntimeError("store unreachable")

    rebac = _UnreachableStore()

    with pytest.raises(RuntimeError, match="store unreachable"):
        await main._initialize_account_standing(_container(rebac))

    assert rebac.calls == ["validate_standing_model", "grant_default_standing"]
    assert STANDING_READY not in rebac.relations
    with pytest.raises(StandingAuthorizationError):
        await rebac.require_user_standing("synthetic-person")


@pytest.mark.asyncio
async def test_unconfirmed_marker_refuses_startup() -> None:
    rebac = _MarkerLandsNowhere()

    with pytest.raises(RuntimeError, match="^Account standing is not ready.$"):
        await main._initialize_account_standing(_container(rebac))

    assert rebac.calls == _STARTUP_CALLS
    assert STANDING_READY not in rebac.relations


class _Container:
    """The container surface `create_app` and its lifespan touch."""

    def __init__(self, rebac: StandingRebacEngine) -> None:
        self._rebac = rebac

    def get_kpi_writer(self):
        from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter

        return NoOpKPIWriter()

    def get_rebac_engine(self) -> StandingRebacEngine:
        return self._rebac

    def start_metrics_exporter(self) -> None:
        return None

    def start_kpi_tasks(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None


def _app_recording_startup(monkeypatch: pytest.MonkeyPatch, rebac: StandingRebacEngine):
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")
    monkeypatch.setattr(
        main, "build_application_container", lambda _: _Container(rebac)
    )
    monkeypatch.setattr(main, "initialize_shared_stores", lambda _: None)
    for step in (
        "_reconcile_team_organization_relations",
        "_reconcile_team_admin_charter_roles",
        "_seed_capability_registration_defaults",
    ):

        async def record(_container, step: str = step) -> None:
            rebac.calls.append(step)

        monkeypatch.setattr(main, step, record)
    return main.create_app()


@pytest.mark.asyncio
@pytest.mark.parametrize("enforced", [True, False])
async def test_lifespan_runs_standing_before_the_startup_reconciliations(
    monkeypatch: pytest.MonkeyPatch, enforced: bool
) -> None:
    rebac = StandingRebacEngine(enforces_standing=enforced)
    app = _app_recording_startup(monkeypatch, rebac)

    async with app.router.lifespan_context(app):
        pass

    reconciliations = [
        "_reconcile_team_organization_relations",
        "_reconcile_team_admin_charter_roles",
        "_seed_capability_registration_defaults",
    ]
    assert rebac.calls == (_STARTUP_CALLS if enforced else []) + reconciliations


@pytest.mark.asyncio
async def test_lifespan_standing_failure_stops_startup_before_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rebac = _MarkerLandsNowhere()
    app = _app_recording_startup(monkeypatch, rebac)

    with pytest.raises(RuntimeError, match="Account standing is not ready."):
        async with app.router.lifespan_context(app):
            pass

    assert rebac.calls == _STARTUP_CALLS
