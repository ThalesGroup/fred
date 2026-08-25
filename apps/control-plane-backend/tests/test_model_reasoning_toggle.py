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

"""Level 2 of REASON-01 (`MODEL-REASONING-ENABLEMENT-RFC.md` §5), control-plane
side: the platform-wide per-model reasoning activation.

Covers the two properties the rest of the feature rests on:

- **absent row = OFF** (§5.6) — the store's read side never invents an
  enablement, which is what makes the upgrade behaviour in §5.6.1 true;
- **aptitude cannot be granted** (§5.3) — the write path refuses a capability
  with no thinking-capable profile, rather than persisting an activation that
  could never take effect.
"""

from __future__ import annotations

from typing import Any

import pytest
from control_plane_backend.capabilities import service as capability_service
from control_plane_backend.capabilities.enablement import (
    CapabilityNotFound,
    ReasoningNotSupported,
)
from control_plane_backend.capabilities.reasoning_store import ModelReasoningStore
from fred_core import KeycloakUser
from fred_core.common import PostgresStoreConfig
from fred_core.sql import create_async_engine_from_config
from fred_sdk.contracts.capability.manifest import CapabilityCatalogEntry

THINKING_MODEL = "model__openai__mistral-small-latest"
PLAIN_MODEL = "model__openai__gpt-4o"


def _user() -> KeycloakUser:
    return KeycloakUser(uid="admin-1", username="admin-1", roles=["admin"], email=None)


async def _make_store(tmp_path) -> ModelReasoningStore:
    from control_plane_backend.models.base import Base as ControlPlaneBase
    from fred_core.models.base import Base as CoreBase

    engine = create_async_engine_from_config(
        PostgresStoreConfig(sqlite_path=str(tmp_path / "model_reasoning.sqlite3"))
    )
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
        await conn.run_sync(ControlPlaneBase.metadata.create_all)
    return ModelReasoningStore(engine=engine)


# ---------------------------------------------------------------------------
# Store — absent row = off (§5.6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_stored_row_means_no_model_reasons(tmp_path) -> None:
    """§5.6 / §5.6.1 in one assertion.

    This empty set is what turns reasoning OFF on upgrade for a deployment that
    ran it through `models_catalog.yaml` alone — release-noted, not silent.
    """

    store = await _make_store(tmp_path)

    assert await store.list_enabled_model_ids() == set()


@pytest.mark.asyncio
async def test_enabling_then_disabling_round_trips(tmp_path) -> None:
    store = await _make_store(tmp_path)

    await store.set_enabled(
        model_capability_id=THINKING_MODEL, reasoning_enabled=True, updated_by="admin-1"
    )
    assert await store.list_enabled_model_ids() == {THINKING_MODEL}

    # Turning it back off must READ as off, not merely stop being true — this
    # is the incident lever (§9), and it has to work on a model that already
    # has a row.
    await store.set_enabled(
        model_capability_id=THINKING_MODEL,
        reasoning_enabled=False,
        updated_by="admin-1",
    )
    assert await store.list_enabled_model_ids() == set()


@pytest.mark.asyncio
async def test_a_stored_false_is_indistinguishable_from_no_row(tmp_path) -> None:
    store = await _make_store(tmp_path)

    await store.set_enabled(
        model_capability_id=PLAIN_MODEL, reasoning_enabled=False, updated_by="admin-1"
    )
    await store.set_enabled(
        model_capability_id=THINKING_MODEL, reasoning_enabled=True, updated_by="admin-1"
    )

    assert await store.list_enabled_model_ids() == {THINKING_MODEL}


# ---------------------------------------------------------------------------
# Service — aptitude is declared, never granted (§5.3)
# ---------------------------------------------------------------------------


def _model_entry(
    capability_id: str,
    *,
    thinking_profile_ids: tuple[str, ...] = (),
    display_name: str | None = None,
) -> CapabilityCatalogEntry:
    return CapabilityCatalogEntry(
        id=capability_id,
        version="1",
        name=capability_id,
        description=capability_id,
        icon="neurology",
        kind="model",
        model_profile_ids=("chat.some.profile",),
        model_thinking_profile_ids=thinking_profile_ids,
        model_display_name=display_name,
    )


class _RecordingStore:
    def __init__(self, enabled: set[str] | None = None) -> None:
        self.writes: list[tuple[str, bool]] = []
        self._enabled = enabled or set()

    async def set_enabled(
        self,
        *,
        model_capability_id: str,
        reasoning_enabled: bool,
        updated_by: str | None,
    ) -> bool:
        self.writes.append((model_capability_id, reasoning_enabled))
        return reasoning_enabled

    async def list_enabled_model_ids(self) -> set[str]:
        return set(self._enabled)


class _FakeDeps:
    """Only the attributes `set_model_reasoning` / `set_default_on` read."""

    def __init__(self, store: _RecordingStore) -> None:
        self._store = store
        self.team_dependencies = type("_TD", (), {"rebac": object()})()

    def get_model_reasoning_store(self) -> Any:
        return self._store

    def get_agent_instance_store(self) -> Any:
        return object()

    def get_kpi_writer(self) -> Any:
        return object()


@pytest.fixture(autouse=True)
def _stub_gate_and_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `can_manage` gate has its own suite; stub it so these tests exercise
    the aptitude rule rather than a second copy of the authorization tests."""

    async def _no_op_gate(rebac, user, capability_id):  # noqa: ANN001
        return None

    catalog = {
        THINKING_MODEL: _model_entry(
            THINKING_MODEL,
            thinking_profile_ids=("chat.mistral.small",),
            display_name="Mistral Small",
        ),
        PLAIN_MODEL: _model_entry(PLAIN_MODEL),
        "doc_access": CapabilityCatalogEntry(
            id="doc_access",
            version="1",
            name="doc_access",
            description="doc_access",
            icon="tune",
        ),
    }

    async def _fake_aggregate(deps):  # noqa: ANN001
        return catalog

    monkeypatch.setattr(capability_service, "_require_can_manage", _no_op_gate)
    monkeypatch.setattr(
        capability_service, "aggregate_capability_catalog", _fake_aggregate
    )


@pytest.mark.asyncio
async def test_enabling_reasoning_on_a_thinking_model_stores_the_row() -> None:
    store = _RecordingStore()

    result = await capability_service.set_model_reasoning(
        user=_user(),
        capability_id=THINKING_MODEL,
        reasoning_enabled=True,
        deps=_FakeDeps(store),  # type: ignore[arg-type]
    )

    assert result.reasoning_enabled is True
    assert store.writes == [(THINKING_MODEL, True)]
    # Nothing else is captured: no display snapshot is taken any more (#2387).


@pytest.mark.asyncio
async def test_a_model_with_no_thinking_profile_is_refused() -> None:
    # §5.3 — an administrator cannot make a model reason. Persisting the row
    # would put a control in the UI that lies about what it does, which is the
    # decorative-flag failure §5.6.2 exists to prevent.
    store = _RecordingStore()

    with pytest.raises(ReasoningNotSupported):
        await capability_service.set_model_reasoning(
            user=_user(),
            capability_id=PLAIN_MODEL,
            reasoning_enabled=True,
            deps=_FakeDeps(store),  # type: ignore[arg-type]
        )

    assert store.writes == []


@pytest.mark.asyncio
async def test_a_non_model_capability_is_refused() -> None:
    store = _RecordingStore()

    with pytest.raises(ReasoningNotSupported):
        await capability_service.set_model_reasoning(
            user=_user(),
            capability_id="doc_access",
            reasoning_enabled=True,
            deps=_FakeDeps(store),  # type: ignore[arg-type]
        )

    assert store.writes == []


@pytest.mark.asyncio
async def test_an_unknown_capability_is_not_found() -> None:
    with pytest.raises(CapabilityNotFound):
        await capability_service.set_model_reasoning(
            user=_user(),
            capability_id="model__openai__does-not-exist",
            reasoning_enabled=True,
            deps=_FakeDeps(_RecordingStore()),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_switching_reasoning_off_is_allowed_and_stored() -> None:
    # The incident lever (§9) must work through the same validated path.
    store = _RecordingStore()

    result = await capability_service.set_model_reasoning(
        user=_user(),
        capability_id=THINKING_MODEL,
        reasoning_enabled=False,
        deps=_FakeDeps(store),  # type: ignore[arg-type]
    )

    assert result.reasoning_enabled is False
    assert store.writes == [(THINKING_MODEL, False)]


# ---------------------------------------------------------------------------
# §5.7 — switching a model OFF switches its reasoning off with it
# ---------------------------------------------------------------------------


@pytest.fixture
def _stub_default_on_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize the ReBAC half of `set_default_on`.

    These tests are about what happens to the reasoning row afterwards; the
    tuple write and its suspension accounting have their own suite.
    """

    async def _no_op_default_on(**kwargs: Any) -> int:
        return 0

    monkeypatch.setattr(
        capability_service, "set_capability_default_on", _no_op_default_on
    )


@pytest.mark.asyncio
async def test_switching_a_model_off_switches_its_reasoning_off(
    _stub_default_on_write: None,
) -> None:
    # The two axes are independent in the other direction only (§5.4): leaving
    # a stored `reasoning_enabled` on a withdrawn model means re-enabling the
    # model later silently brings reasoning back.
    store = _RecordingStore(enabled={THINKING_MODEL})

    result = await capability_service.set_default_on(
        user=_user(),
        capability_id=THINKING_MODEL,
        default_on=False,
        deps=_FakeDeps(store),  # type: ignore[arg-type]
    )

    assert store.writes == [(THINKING_MODEL, False)]
    # Reported, not silent — the admin's row changes in two places at once.
    assert result.reasoning_disabled is True


@pytest.mark.asyncio
async def test_switching_a_model_off_writes_no_row_when_reasoning_was_never_on(
    _stub_default_on_write: None,
) -> None:
    # An absent row and a stored `false` mean the same thing (§5.6), so the
    # cascade must not stamp a row on every model an admin ever switches off.
    store = _RecordingStore(enabled=set())

    result = await capability_service.set_default_on(
        user=_user(),
        capability_id=THINKING_MODEL,
        default_on=False,
        deps=_FakeDeps(store),  # type: ignore[arg-type]
    )

    assert store.writes == []
    assert result.reasoning_disabled is False


@pytest.mark.asyncio
async def test_switching_a_model_on_does_not_switch_its_reasoning_on(
    _stub_default_on_write: None,
) -> None:
    # The cascade is one-directional on purpose: reasoning stays an explicit
    # second decision (§5.4), it is never granted as a side effect of access.
    store = _RecordingStore(enabled=set())
    deps = _FakeDeps(store)
    # No instance holds this capability, so the revive sweep the ON path runs
    # finds no team and this test stays about the reasoning row.
    deps.get_agent_instance_store = type(  # type: ignore[method-assign]
        "_S", (), {"list_all": staticmethod(_empty_list)}
    )

    result = await capability_service.set_default_on(
        user=_user(),
        capability_id=THINKING_MODEL,
        default_on=True,
        deps=deps,  # type: ignore[arg-type]
    )

    assert store.writes == []
    assert result.reasoning_disabled is False


async def _empty_list() -> list[Any]:
    return []


# ---------------------------------------------------------------------------
# §7/§8 — the composer control is emitted by the PLATFORM, and only when every
# upstream gate is open
# ---------------------------------------------------------------------------


def test_no_control_when_the_agent_does_not_offer_reasoning() -> None:
    # Level 3 lives on the agent itself (`tuning.reasoning_enabled`, set in the
    # General section of the agent form) — NOT in the capability/tool system:
    # an agent does not "use" reasoning the way it uses a tool.
    from control_plane_backend.product.service import _platform_reasoning_control

    assert (
        _platform_reasoning_control(
            reasoning_enabled=False,
            reasoning_default_on=False,
            reasoning_enabled_model_ids=[THINKING_MODEL],
        )
        is None
    )


def test_no_control_when_no_model_reasons_platform_wide() -> None:
    """§8's diagnosability rule.

    Three of the four gates are invisible from the chat page. If no model's
    reasoning is on, the toggle provably cannot do anything — so it must be
    ABSENT, or the predictable support ticket is "I turned reasoning on and
    nothing happened" with no way to tell which gate blocked.
    """

    from control_plane_backend.product.service import _platform_reasoning_control

    assert (
        _platform_reasoning_control(
            reasoning_enabled=True,
            reasoning_default_on=False,
            reasoning_enabled_model_ids=[],
        )
        is None
    )


def test_control_is_emitted_when_every_gate_is_open() -> None:
    from control_plane_backend.product.service import (
        PLATFORM_CHAT_CONTROL_OWNER,
        _platform_reasoning_control,
    )

    control = _platform_reasoning_control(
        reasoning_enabled=True,
        reasoning_default_on=False,
        reasoning_enabled_model_ids=[THINKING_MODEL],
    )

    assert control is not None
    assert control.widget == "reasoning_toggle"
    # No owning capability: reasoning is a platform chat option, so the
    # descriptor carries the reserved sentinel owner rather than a capability id.
    assert control.capability_id == PLATFORM_CHAT_CONTROL_OWNER
    # Default OFF is a safety decision, not a style one: Amendment C measured
    # reasoning re-issuing duplicate tool calls in 10/10 turns on this stack.
    # Author-settable since Amendment B, but this stays the value an author
    # who does nothing gets. No model identity rides along any more (#2387) —
    # see test_params_never_carry_a_model_identity below.
    assert control.params == {"default": False}


def test_params_carry_only_the_starting_value() -> None:
    """#2387 — the control is a plain on/off switch and says nothing more.

    It used to ship `model_id`/`display_name` (the single reasoning-enabled
    model's identity, which the composer rendered as its model label) and
    `effort` (that model's ops-authored `settings.reasoning_effort`). The
    identity was wrong — it named the model whose REASONING was on, not the one
    a turn routes to — and the effort went with it when the menu became a plain
    on/off. The level a turn runs with stays the pod's business: it applies the
    live settings value either way.
    """

    from control_plane_backend.product.service import _platform_reasoning_control

    control = _platform_reasoning_control(
        reasoning_enabled=True,
        reasoning_default_on=False,
        reasoning_enabled_model_ids=[THINKING_MODEL],
    )
    assert control is not None
    assert control.params == {"default": False}

    # Several enabled models change nothing — there is no per-model value left
    # to disagree about, which is the point of removing them.
    two = _platform_reasoning_control(
        reasoning_enabled=True,
        reasoning_default_on=False,
        reasoning_enabled_model_ids=[THINKING_MODEL, PLAIN_MODEL],
    )
    assert two is not None
    assert two.params == {"default": False}


# ---------------------------------------------------------------------------
# Amendment B — the author decides where the composer's switch STARTS
# ---------------------------------------------------------------------------


def test_author_can_preselect_reasoning_on_new_conversations() -> None:
    """`reasoning_default_on` seeds `params.default`, which `useComposerSettings`
    reads as the composer's initial value for a fresh session."""

    from control_plane_backend.product.service import _platform_reasoning_control

    control = _platform_reasoning_control(
        reasoning_enabled=True,
        reasoning_default_on=True,
        reasoning_enabled_model_ids=[THINKING_MODEL],
    )

    assert control is not None
    assert control.params == {"default": True}


def test_preselect_cannot_conjure_a_control_the_gates_refused() -> None:
    """Amendment B decides where the switch starts, never whether there is one.

    The failure this guards against is an author leaving the default ON, then
    withdrawing the offer, and reasoning silently staying on for users — §8's
    gates must still win, and the stored value must stay inert.
    """

    from control_plane_backend.product.service import _platform_reasoning_control

    assert (
        _platform_reasoning_control(
            reasoning_enabled=False,
            reasoning_default_on=True,
            reasoning_enabled_model_ids=[THINKING_MODEL],
        )
        is None
    )
    assert (
        _platform_reasoning_control(
            reasoning_enabled=True,
            reasoning_default_on=True,
            reasoning_enabled_model_ids=[],
        )
        is None
    )
