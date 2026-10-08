"""Control-plane startup of account status (`enforce_account_status`).

A person's account is active unless the store holds their `suspended` tuple, so
startup writes nothing: with a delegation switch on it validates the selected
authorization model, refuses to start when that model cannot record a
suspension, and installs the engine for each request's account status check. The
lifespan runs this step before the startup reconciliations.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from _account_status_test_doubles import AccountStatusRebacEngine, ban
from control_plane_backend import main
from fred_core import (
    AccountStatusError,
    DelegationConfig,
    KeycloakUser,
    OpenFgaRebacConfig,
    OpenFgaRebacEngine,
    enforce_account_status,
    initialize_delegation,
)
from fred_core.security.delegation import require_active_subject
from fred_core.security.rebac.openfga_schema import DEFAULT_SCHEMA
from openfga_sdk.api_client import ApiClient
from openfga_sdk.configuration import Configuration

_STARTUP_CALLS = ["validate_account_status_model"]
_MODEL_UNAVAILABLE = "^Account status authorization model is not available.$"
_PERSON = KeycloakUser(uid="synthetic-person", username="synthetic", roles=[])
_SWITCHES = pytest.mark.parametrize(
    "switch",
    [
        DelegationConfig(act_for_people=True),
        DelegationConfig(accept_delegated_calls=True),
        DelegationConfig(),
    ],
    ids=["act_for_people", "accept_delegated_calls", "local_without_delegation"],
)


class _UnsupportedModel(AccountStatusRebacEngine):
    async def validate_account_status_model(self) -> None:
        await super().validate_account_status_model()
        raise RuntimeError("Account status authorization model is not available.")


class _OpenFgaStore:
    """The OpenFGA client surface startup may reach: model reads, parsed by the
    SDK itself, and writes. Any other call fails the test on the missing attribute."""

    def __init__(self, model: dict) -> None:
        self.model = model
        self.model_reads = 0
        self.writes: list[object] = []

    async def read_authorization_model(self, options):
        self.model_reads += 1
        payload = {
            "authorization_model": {
                "id": options["authorization_model_id"],
                **self.model,
            }
        }
        async with ApiClient(Configuration(api_url="http://openfga.invalid")) as api:
            return api.deserialize(
                SimpleNamespace(data=json.dumps(payload)),
                "ReadAuthorizationModelResponse",
            )

    async def read_latest_authorization_model(self):
        return await self.read_authorization_model(
            {"authorization_model_id": "synthetic-model"}
        )

    async def write(self, body, options):
        self.writes.append(body)


def _shipped_model() -> dict:
    return json.loads(DEFAULT_SCHEMA)


def _model_without_suspended() -> dict:
    model = _shipped_model()
    organization = next(
        definition
        for definition in model["type_definitions"]
        if definition["type"] == "platform"
    )
    del organization["relations"]["suspended"]
    del organization["metadata"]["relations"]["suspended"]
    return model


def _openfga_engine(store: _OpenFgaStore) -> OpenFgaRebacEngine:
    engine = OpenFgaRebacEngine(
        OpenFgaRebacConfig(
            api_url="http://openfga.invalid",  # pyright: ignore[reportArgumentType]
        ),
        token="synthetic-token",  # nosec B106 - synthetic fixture
        requires_active_accounts=True,
    )
    engine._cached_client = store  # pyright: ignore[reportAttributeAccessIssue]
    return engine


@pytest.mark.asyncio
@_SWITCHES
async def test_startup_validates_the_model_and_writes_nothing(
    switch: DelegationConfig,
) -> None:
    initialize_delegation(switch)
    rebac = AccountStatusRebacEngine()

    await enforce_account_status(rebac)

    assert rebac.calls == _STARTUP_CALLS
    assert rebac.relations == set()
    # A person with no stored tuple passes the request's real account status check.
    await require_active_subject(_PERSON)


@pytest.mark.asyncio
async def test_startup_over_a_stored_suspension_keeps_that_person_refused() -> None:
    initialize_delegation(DelegationConfig(act_for_people=True))
    rebac = AccountStatusRebacEngine(relations={ban("synthetic-suspended-person")})

    await enforce_account_status(rebac)
    await enforce_account_status(rebac)

    assert rebac.relations == {ban("synthetic-suspended-person")}
    with pytest.raises(AccountStatusError) as refused:
        await require_active_subject(
            _PERSON.model_copy(update={"uid": "synthetic-suspended-person"})
        )
    assert refused.value.unavailable is False
    await require_active_subject(_PERSON)


@pytest.mark.asyncio
async def test_startup_makes_no_account_status_call_with_both_switches_off() -> None:
    initialize_delegation(DelegationConfig())
    rebac = AccountStatusRebacEngine(requires_active_accounts=False)

    await enforce_account_status(rebac)

    assert rebac.calls == []
    assert rebac.relations == set()


@pytest.mark.asyncio
@_SWITCHES
async def test_model_validation_failure_refuses_startup_and_writes_nothing(
    switch: DelegationConfig,
) -> None:
    initialize_delegation(switch)
    rebac = _UnsupportedModel()

    with pytest.raises(RuntimeError, match=_MODEL_UNAVAILABLE):
        await enforce_account_status(rebac)

    assert rebac.calls == _STARTUP_CALLS
    assert rebac.relations == set()
    with pytest.raises(AccountStatusError) as refused:
        await require_active_subject(_PERSON)
    assert refused.value.unavailable is True


@pytest.mark.asyncio
async def test_openfga_startup_accepts_the_shipped_model_without_writing() -> None:
    initialize_delegation(DelegationConfig(act_for_people=True))
    store = _OpenFgaStore(_shipped_model())

    await enforce_account_status(_openfga_engine(store))

    assert store.model_reads == 1
    assert store.writes == []


@pytest.mark.asyncio
async def test_openfga_startup_refuses_a_model_without_suspended() -> None:
    initialize_delegation(DelegationConfig(act_for_people=True))
    store = _OpenFgaStore(_model_without_suspended())

    with pytest.raises(RuntimeError, match=_MODEL_UNAVAILABLE):
        await enforce_account_status(_openfga_engine(store))

    assert store.model_reads == 1
    assert store.writes == []


class _Container:
    """The container surface `create_app` and its lifespan touch."""

    def __init__(self, rebac: AccountStatusRebacEngine) -> None:
        self._rebac = rebac

    def get_kpi_writer(self):
        from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter

        return NoOpKPIWriter()

    def get_rebac_engine(self) -> AccountStatusRebacEngine:
        return self._rebac

    def start_metrics_exporter(self) -> None:
        return None

    def start_kpi_tasks(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None


def _app_recording_startup(
    monkeypatch: pytest.MonkeyPatch, rebac: AccountStatusRebacEngine
):
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")
    monkeypatch.setattr(
        main, "build_application_container", lambda _: _Container(rebac)
    )
    monkeypatch.setattr(main, "initialize_shared_stores", lambda _: None)
    for step in (
        "_reconcile_team_admin_charter_roles",
        "_seed_capability_registration_defaults",
    ):

        async def record(_container, step: str = step) -> None:
            rebac.calls.append(step)

        monkeypatch.setattr(main, step, record)
    return main.create_app()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "switch",
    [
        DelegationConfig(),
        DelegationConfig(act_for_people=True),
        DelegationConfig(accept_delegated_calls=True),
    ],
    ids=["off", "act_for_people", "accept_delegated_calls"],
)
@pytest.mark.parametrize("local_directory", [False, True])
async def test_lifespan_installs_the_engine_before_the_startup_reconciliations(
    monkeypatch: pytest.MonkeyPatch, switch: DelegationConfig, local_directory: bool
) -> None:
    rebac = AccountStatusRebacEngine(
        requires_active_accounts=local_directory or switch.in_use
    )
    app = _app_recording_startup(monkeypatch, rebac)
    # After create_app, which installs the configuration's own delegation block.
    initialize_delegation(switch)

    async with app.router.lifespan_context(app):
        await require_active_subject(_PERSON)

    reconciliations = [
        "_reconcile_team_admin_charter_roles",
        "_seed_capability_registration_defaults",
    ]
    assert (
        rebac.calls
        == (_STARTUP_CALLS if rebac.requires_active_accounts else []) + reconciliations
    )
    assert rebac.relations == set()


@pytest.mark.asyncio
async def test_lifespan_model_validation_failure_stops_startup_before_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rebac = _UnsupportedModel()
    app = _app_recording_startup(monkeypatch, rebac)
    initialize_delegation(DelegationConfig(act_for_people=True))

    with pytest.raises(RuntimeError, match=_MODEL_UNAVAILABLE):
        async with app.router.lifespan_context(app):
            pass

    assert rebac.calls == _STARTUP_CALLS
