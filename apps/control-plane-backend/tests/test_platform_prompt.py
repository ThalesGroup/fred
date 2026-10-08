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
Platform-wide platform prompt.

The distinction these tests exist to pin: **row absent** ("no admin ever saved
one" — pods fall back to their own `config/platform_prompt.json`) is NOT the
same as **row present with an empty string** ("an admin deliberately suppressed
the block"). Every layer has to keep them apart, because collapsing them would
silently resurrect the pod default for an admin who meant to turn the block off.

The second half pins the surface's authorization: it asks for the narrow
`can_edit_platform_prompt`, never the `can_manage_platform` catch-all it used
to share with import/export, tasks and platform reset.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from control_plane_backend.platform_prompt.schemas import (
    PLATFORM_PROMPT_MAX_CHARS,
    CreationAssistantModelOption,
    SetCreationAssistantSettingsRequest,
    SetPlatformPromptRequest,
)
from control_plane_backend.platform_prompt.service import (
    PodPlatformPromptFile,
    _to_platform_prompt,
    get_creation_assistant_settings,
    get_platform_instructions,
    get_platform_prompt,
    reset_creation_assistant_prompt,
    resolve_creation_assistant_settings,
    resolve_platform_prompt_text,
    set_creation_assistant_settings,
    set_platform_prompt,
)
from control_plane_backend.platform_prompt.store import (
    StoredCreationAssistantSettings,
    StoredPlatformPrompt,
)
from fastapi import HTTPException
from fred_core import AuthorizationError, KeycloakUser, OrganizationPermission
from fred_core.security.models import Resource
from fred_sdk.contracts.agent_draft import MAX_CREATION_ASSISTANT_PROMPT_CHARS


class _Store:
    def __init__(self, stored: StoredPlatformPrompt | None) -> None:
        self._stored = stored

    async def get(self) -> StoredPlatformPrompt | None:
        return self._stored


def _deps(stored: StoredPlatformPrompt | None) -> SimpleNamespace:
    return SimpleNamespace(get_platform_prompt_store=lambda: _Store(stored))


# ---------------------------------------------------------------------------
# Projection: absent row vs stored empty string
# ---------------------------------------------------------------------------


def test_absent_row_projects_the_pods_default() -> None:
    # The admin editor must open on the text agents are ACTUALLY receiving.
    # Reporting "" here is what left the page showing a blank box on a fresh
    # deployment, implying no platform prompt was in force when one was.
    projected = _to_platform_prompt(None, pod_default="POD-TEXT")

    assert projected.is_default is True
    assert projected.text == "POD-TEXT"
    assert projected.source_unavailable is False
    assert projected.updated_by is None


def test_absent_row_with_no_reachable_pod_says_so() -> None:
    # An empty editor and "we could not ask any pod" look identical to a reader
    # unless the response distinguishes them. Collapsing the two would tell an
    # admin the deployment has no platform prompt during a pod outage.
    projected = _to_platform_prompt(None, pod_default=None)

    assert projected.is_default is True
    assert projected.text == ""
    assert projected.source_unavailable is True


def test_stored_empty_string_is_not_reported_as_default() -> None:
    # `is_default` must differ from the cases above, AND the pod default must
    # not leak into `text` here — this is the admin who turned the block off,
    # and showing them the pod's default would misreport their own decision
    # back to them.
    projected = _to_platform_prompt(
        StoredPlatformPrompt(text="", updated_by="admin", updated_at=None),
        pod_default="POD-TEXT",
    )

    assert projected.is_default is False
    assert projected.text == ""
    assert projected.source_unavailable is False
    assert projected.updated_by == "admin"


def test_a_saved_row_never_reports_source_unavailable() -> None:
    # A stored value answers on its own, so an unreachable pod is irrelevant to
    # it — flagging it would send the UI into a degraded state for nothing.
    projected = _to_platform_prompt(
        StoredPlatformPrompt(text="MINE", updated_by="admin", updated_at=None),
        pod_default=None,
    )

    assert projected.text == "MINE"
    assert projected.source_unavailable is False


# ---------------------------------------------------------------------------
# Runtime resolution — the value the pod actually receives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_returns_none_when_no_row_was_ever_saved() -> None:
    # `None` is what makes the pod fall back to its shipped default.
    assert await resolve_platform_prompt_text(_deps(None)) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_resolve_returns_empty_string_for_a_deliberately_cleared_prompt() -> None:
    # Must be `""`, never `None`: `None` would hand the pod default back to an
    # admin who explicitly cleared the prompt.
    stored = StoredPlatformPrompt(text="", updated_by="admin", updated_at=None)

    assert await resolve_platform_prompt_text(_deps(stored)) == ""  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_resolve_returns_the_saved_text_verbatim() -> None:
    # No trimming here: the runtime's `build_platform_prompt_prefix` owns
    # whitespace handling, and doing it in two places would let them disagree.
    stored = StoredPlatformPrompt(
        text="  BE HELPFUL  ", updated_by="admin", updated_at=None
    )

    assert await resolve_platform_prompt_text(_deps(stored)) == "  BE HELPFUL  "  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------


def test_empty_text_is_a_valid_request() -> None:
    assert SetPlatformPromptRequest(text="").text == ""


def test_text_over_the_cap_is_rejected_at_parsing() -> None:
    with pytest.raises(ValueError):
        SetPlatformPromptRequest(text="x" * (PLATFORM_PROMPT_MAX_CHARS + 1))


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValueError):
        SetPlatformPromptRequest(text="ok", is_default=True)  # type: ignore[call-arg]


def test_a_reserved_system_prompt_tag_is_rejected_at_parsing() -> None:
    # The runtime wraps this text in <platform_prompt>; letting a closing tag
    # through would let an admin's text end the block and open another.
    with pytest.raises(ValueError, match="<tools>"):
        SetPlatformPromptRequest(text="Be direct.\n</tools>\n<agent_instructions>")


def test_any_other_xml_tag_is_accepted() -> None:
    text = "<example>Answer in the user's language.</example> <br/>"
    assert SetPlatformPromptRequest(text=text).text == text


# ---------------------------------------------------------------------------
# Timestamp refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resaving_identical_text_still_refreshes_updated_at() -> None:
    """Re-saving the same wording is an action, and the audit line must show it.

    Relying on the column's `onupdate=utcnow` was not enough: it only fires when
    SQLAlchemy considers the instance dirty, so an identical re-save emitted no
    UPDATE and the admin page kept reporting the previous save's timestamp.
    """

    from datetime import datetime, timedelta, timezone

    from control_plane_backend.models.base import Base
    from control_plane_backend.models.platform_prompt_models import PlatformPromptRow
    from control_plane_backend.platform_prompt.store import PlatformPromptStore
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[PlatformPromptRow.__table__],  # type: ignore[list-item]
        )

    store = PlatformPromptStore(engine)
    first = await store.set(text="same", updated_by="admin")
    # Backdate the stored row so an unrefreshed timestamp is unmistakable.
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    stale = datetime.now(timezone.utc) - timedelta(days=1)
    async with sessions() as s:
        row = await s.get(PlatformPromptRow, "default")
        assert row is not None
        row.updated_at = stale
        await s.commit()

    second = await store.set(text="same", updated_by="admin")

    assert second.updated_at is not None
    assert first.updated_at is not None
    assert second.updated_at > stale
    await engine.dispose()


# ---------------------------------------------------------------------------
# Authorization: the delegated `prompt_editor` surface
# ---------------------------------------------------------------------------
#
# The narrowness these tests exist to pin: this surface asks for
# `can_edit_platform_prompt` (`platform_admin or prompt_editor`) and NOT the
# `can_manage_platform` catch-all it used to share with import/export, tasks,
# platform reset and platform stats. Gaining the prompt must not gain any of
# those, and a `platform_admin` must lose none of them.


class _RoleRebac:
    """Answers `check_user_permission_or_raise` from a fixed permission set —
    the tuples one role actually holds, per `schema.fga`."""

    def __init__(self, *allowed: OrganizationPermission) -> None:
        self._allowed = set(allowed)
        self.asked: list[OrganizationPermission] = []

    async def check_user_permission_or_raise(
        self, user, permission, resource_id, **kwargs
    ) -> None:
        self.asked.append(permission)
        if permission not in self._allowed:
            raise AuthorizationError(
                user.uid, str(permission), Resource.ORGANIZATION, "denied"
            )


def _prompt_editor() -> _RoleRebac:
    """A user holding `organization#prompt_editor` and nothing else. Reaches
    `can_edit_platform_prompt` through the schema union; `can_manage_platform`
    stays `platform_admin`-only (pinned in fred-core's schema tests)."""

    return _RoleRebac(OrganizationPermission.CAN_EDIT_PLATFORM_PROMPT)


def _platform_admin() -> _RoleRebac:
    return _RoleRebac(
        OrganizationPermission.CAN_EDIT_PLATFORM_PROMPT,
        OrganizationPermission.CAN_MANAGE_PLATFORM,
    )


class _WritableStore(_Store):
    def __init__(self, stored: StoredPlatformPrompt | None = None) -> None:
        super().__init__(stored)
        self.written: list[str] = []

    async def set(self, *, text: str, updated_by: str | None) -> StoredPlatformPrompt:
        self.written.append(text)
        self._stored = StoredPlatformPrompt(
            text=text, updated_by=updated_by, updated_at=None
        )
        return self._stored


def _authz_deps(rebac: _RoleRebac, store: _Store) -> SimpleNamespace:
    """`ProductServiceDependencies` stand-in: the gate, the store, and an empty
    runtime source list so the pod fetch resolves offline."""

    return SimpleNamespace(
        get_platform_prompt_store=lambda: store,
        team_dependencies=SimpleNamespace(rebac=rebac),
        configuration=SimpleNamespace(
            platform=SimpleNamespace(runtime_catalog_sources=[])
        ),
    )


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u", username="u", roles=[], email=None)


@pytest.mark.asyncio
async def test_prompt_editor_reads_the_platform_prompt() -> None:
    rebac = _prompt_editor()
    stored = StoredPlatformPrompt(text="SAVED", updated_by="a", updated_at=None)

    result = await get_platform_prompt(
        user=_user(),
        deps=_authz_deps(rebac, _Store(stored)),  # type: ignore[arg-type]
    )

    assert result.text == "SAVED"
    assert rebac.asked == [OrganizationPermission.CAN_EDIT_PLATFORM_PROMPT]


@pytest.mark.asyncio
async def test_prompt_editor_updates_the_platform_prompt() -> None:
    # Reading without writing would make the role pointless; this is the whole
    # surface the role exists to own.
    rebac = _prompt_editor()
    store = _WritableStore()

    result = await set_platform_prompt(
        user=_user(),
        text="NEW",
        deps=_authz_deps(rebac, store),  # type: ignore[arg-type]
    )

    assert store.written == ["NEW"]
    assert result.text == "NEW"
    assert rebac.asked == [OrganizationPermission.CAN_EDIT_PLATFORM_PROMPT]


@pytest.mark.asyncio
async def test_prompt_editor_reads_the_shipped_instructions() -> None:
    # The read-only pane is the reference the editor writes against — gating it
    # higher than the editor itself would leave them writing blind.
    rebac = _prompt_editor()

    result = await get_platform_instructions(
        user=_user(),
        deps=_authz_deps(rebac, _Store(None)),  # type: ignore[arg-type]
    )

    assert result.source_unavailable is True
    assert rebac.asked == [OrganizationPermission.CAN_EDIT_PLATFORM_PROMPT]


@pytest.mark.asyncio
async def test_a_user_without_the_relation_is_denied_on_every_entry_point() -> None:
    rebac = _RoleRebac()
    deps = _authz_deps(rebac, _WritableStore())

    for call in (
        lambda: get_platform_prompt(user=_user(), deps=deps),  # type: ignore[arg-type]
        lambda: set_platform_prompt(user=_user(), text="x", deps=deps),  # type: ignore[arg-type]
        lambda: get_platform_instructions(user=_user(), deps=deps),  # type: ignore[arg-type]
    ):
        with pytest.raises(AuthorizationError):
            await call()


@pytest.mark.asyncio
async def test_platform_admin_still_reaches_the_whole_surface() -> None:
    # The schema union (`prompt_editor: [user] or platform_admin`) is what makes
    # this hold; carving the relation out must not have cost an admin a surface.
    rebac = _platform_admin()
    store = _WritableStore()
    deps = _authz_deps(rebac, store)

    await get_platform_prompt(user=_user(), deps=deps)  # type: ignore[arg-type]
    await set_platform_prompt(user=_user(), text="ADMIN", deps=deps)  # type: ignore[arg-type]
    await get_platform_instructions(user=_user(), deps=deps)  # type: ignore[arg-type]

    assert store.written == ["ADMIN"]


@pytest.mark.asyncio
async def test_prompt_editor_cannot_reach_a_can_manage_platform_surface() -> None:
    """The narrowness regression: the role must buy the prompt and nothing else.

    Platform stats stands in for the whole catch-all family (import, export,
    reset, tasks) — they all check `CAN_MANAGE_PLATFORM` on the organization
    singleton through the same call. The gate runs before any dependency is
    touched, so the unused ones can be `None`.
    """

    from control_plane_backend.import_export.api import build_import_export_router

    router = build_import_export_router()
    endpoint = next(
        route.endpoint  # type: ignore[attr-defined]
        for route in router.routes
        if getattr(route, "name", None) == "platform_stats"
    )

    with pytest.raises(AuthorizationError):
        await endpoint(
            user=_user(), team_deps=None, engine=None, rebac=_prompt_editor()
        )


# ---------------------------------------------------------------------------
# Creation assistant settings: meta-prompt override and model
# ---------------------------------------------------------------------------

_OPTIONS = [
    CreationAssistantModelOption(profile_id="chat.large", name="Large"),
    CreationAssistantModelOption(profile_id="chat.small", name="Small"),
]


class _AssistantStore:
    def __init__(self, stored: StoredCreationAssistantSettings | None = None) -> None:
        self._stored = stored

    async def get(self) -> StoredCreationAssistantSettings | None:
        return self._stored

    async def set(
        self,
        *,
        text: str | None,
        model_profile_id: str | None,
        reasoning_effort: Any = "off",
        updated_by: str | None,
    ) -> StoredCreationAssistantSettings:
        self._stored = StoredCreationAssistantSettings(
            text=text,
            model_profile_id=model_profile_id,
            reasoning_effort=reasoning_effort,
            updated_by=updated_by,
            updated_at=None,
        )
        return self._stored


def _assistant_deps(
    rebac: _RoleRebac,
    store: object,
    pod_default: str | None = "DEFAULT {language}",
    revised_at: date | None = None,
) -> Any:
    async def _fetch(_deps: object) -> PodPlatformPromptFile | None:
        if pod_default is None:
            return None
        return PodPlatformPromptFile(
            platform_prompt="",
            platform_instructions="",
            creation_assistant_prompt=pod_default,
            creation_assistant_prompt_revised_at=revised_at,
        )

    deps = _authz_deps(rebac, _Store(None))
    deps.get_creation_assistant_settings_store = lambda: store
    deps._fetch = _fetch
    return deps


@pytest.fixture
def _pod_file(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fetch(deps):  # type: ignore[no-untyped-def]
        return await deps._fetch(deps)

    async def _models(_deps):  # type: ignore[no-untyped-def]
        return _OPTIONS, "chat.large"

    service = "control_plane_backend.platform_prompt.service"
    monkeypatch.setattr(f"{service}.fetch_pod_platform_prompt_file", _fetch)
    monkeypatch.setattr(f"{service}._creation_assistant_models", _models)


@pytest.mark.asyncio
async def test_creation_assistant_settings_store_round_trip() -> None:
    from control_plane_backend.models.base import Base
    from control_plane_backend.models.platform_prompt_models import (
        CreationAssistantSettingsRow,
    )
    from control_plane_backend.platform_prompt.store import (
        CreationAssistantSettingsStore,
    )
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[CreationAssistantSettingsRow.__table__],  # type: ignore[list-item]
        )
    store = CreationAssistantSettingsStore(engine)

    assert await store.get() is None
    await store.set(text="ONE", model_profile_id=None, updated_by="a")
    assert (await store.get()).reasoning_effort == "off"  # type: ignore[union-attr]
    await store.set(
        text=None,
        model_profile_id="chat.large",
        reasoning_effort="high",
        updated_by="b",
    )
    stored = await store.get()
    assert stored is not None
    assert (
        stored.text,
        stored.model_profile_id,
        stored.reasoning_effort,
        stored.updated_by,
    ) == (None, "chat.large", "high", "b")
    assert stored.updated_at is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_creation_assistant_settings_column_defaults_to_reasoning_off() -> None:
    from control_plane_backend.models.base import Base
    from control_plane_backend.models.platform_prompt_models import (
        CreationAssistantSettingsRow,
    )
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[CreationAssistantSettingsRow.__table__],  # type: ignore[list-item]
        )
        # A row written without the column gets the server default.
        await conn.execute(
            text(
                "INSERT INTO creation_assistant_settings (id, updated_at) "
                "VALUES ('default', CURRENT_TIMESTAMP)"
            )
        )
        effort = await conn.scalar(
            text("SELECT reasoning_effort FROM creation_assistant_settings")
        )
    assert effort == "off"
    await engine.dispose()


@pytest.mark.asyncio
async def test_creation_assistant_settings_default_to_the_pod(_pod_file) -> None:
    rebac = _prompt_editor()
    deps = _assistant_deps(rebac, _AssistantStore())

    result = await get_creation_assistant_settings(user=_user(), deps=deps)

    assert result.text == result.default_text == "DEFAULT {language}"
    assert result.is_default is True
    assert result.source_unavailable is False
    assert result.missing_language_placeholder is False
    assert result.model_profile_id is None
    assert result.model_options == _OPTIONS
    assert result.reasoning_effort == "off"
    assert result.default_model_profile_id == "chat.large"
    assert rebac.asked == [OrganizationPermission.CAN_EDIT_PLATFORM_PROMPT]


@pytest.mark.asyncio
async def test_creation_assistant_settings_older_pod_reports_source_unavailable(
    _pod_file,
) -> None:
    deps = _assistant_deps(_prompt_editor(), _AssistantStore(), pod_default=None)

    result = await get_creation_assistant_settings(user=_user(), deps=deps)

    assert result.text == "" and result.default_text is None
    assert result.source_unavailable is True


@pytest.mark.asyncio
async def test_creation_assistant_save_flags_a_missing_placeholder_and_reset_keeps_the_model(
    _pod_file,
) -> None:
    deps = _assistant_deps(_prompt_editor(), _AssistantStore())

    saved = await set_creation_assistant_settings(
        user=_user(),
        text="NO PLACEHOLDER",
        model_profile_id="chat.small",
        reasoning_effort="off",
        deps=deps,
    )
    assert saved.text == "NO PLACEHOLDER"
    assert saved.is_default is False
    assert saved.default_text == "DEFAULT {language}"
    assert saved.missing_language_placeholder is True
    assert saved.model_profile_id == "chat.small"
    assert saved.reasoning_effort == "off"
    stored = await resolve_creation_assistant_settings(deps)
    assert stored is not None and stored.text == "NO PLACEHOLDER"

    reset = await reset_creation_assistant_prompt(user=_user(), deps=deps)
    assert reset.is_default is True and reset.text == "DEFAULT {language}"
    assert (reset.model_profile_id, reset.reasoning_effort) == ("chat.small", "off")
    stored = await resolve_creation_assistant_settings(deps)
    assert stored is not None
    assert (stored.text, stored.model_profile_id, stored.reasoning_effort) == (
        None,
        "chat.small",
        "off",
    )


@pytest.mark.asyncio
async def test_creation_assistant_model_only_keeps_the_built_in_text(_pod_file) -> None:
    deps = _assistant_deps(_prompt_editor(), _AssistantStore())

    saved = await set_creation_assistant_settings(
        user=_user(), text=None, model_profile_id="chat.large", deps=deps
    )

    assert saved.is_default is True and saved.text == "DEFAULT {language}"
    assert saved.model_profile_id == "chat.large"


@pytest.mark.asyncio
async def test_creation_assistant_refuses_a_model_outside_the_catalog(
    _pod_file,
) -> None:
    store = _AssistantStore()
    deps = _assistant_deps(_prompt_editor(), store)

    with pytest.raises(HTTPException) as exc:
        await set_creation_assistant_settings(
            user=_user(), text=None, model_profile_id="chat.gone", deps=deps
        )

    assert exc.value.status_code == 422
    assert await store.get() is None


@pytest.mark.asyncio
async def test_creation_assistant_keeps_a_stored_model_the_catalog_lost(
    _pod_file,
) -> None:
    store = _AssistantStore(
        StoredCreationAssistantSettings(
            text="OLD",
            model_profile_id="chat.gone",
            reasoning_effort="medium",
            updated_by="a",
            updated_at=None,
        )
    )
    deps = _assistant_deps(_prompt_editor(), store)

    saved = await set_creation_assistant_settings(
        user=_user(), text="NEW {language}", model_profile_id="chat.gone", deps=deps
    )

    assert (saved.text, saved.model_profile_id) == ("NEW {language}", "chat.gone")
    with pytest.raises(HTTPException) as exc:
        await set_creation_assistant_settings(
            user=_user(), text="NEW", model_profile_id="chat.other", deps=deps
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_a_model_only_change_keeps_the_override_date() -> None:
    from datetime import timedelta

    from control_plane_backend.models.base import Base
    from control_plane_backend.models.platform_prompt_models import (
        CreationAssistantSettingsRow,
    )
    from control_plane_backend.platform_prompt.store import (
        CreationAssistantSettingsStore,
    )
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[CreationAssistantSettingsRow.__table__],  # type: ignore[list-item]
        )
    store = CreationAssistantSettingsStore(engine)
    await store.set(text="MINE", model_profile_id=None, updated_by="a")
    stale = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        row = await s.get(CreationAssistantSettingsRow, "default")
        assert row is not None
        row.updated_at = stale
        await s.commit()

    model_only = await store.set(text="MINE", model_profile_id="m", updated_by="b")
    stored = await store.get()
    assert stored is not None
    assert stored.model_profile_id == "m"
    assert (stored.updated_by, model_only.updated_by) == ("a", "a")
    assert stored.updated_at is not None
    assert stored.updated_at.replace(tzinfo=timezone.utc) == stale

    reasoning_only = await store.set(
        text="MINE", model_profile_id="m", reasoning_effort="high", updated_by="c"
    )
    assert reasoning_only.reasoning_effort == "high"
    assert reasoning_only.updated_by == "a"
    assert reasoning_only.updated_at is not None
    assert reasoning_only.updated_at.replace(tzinfo=timezone.utc) == stale

    resaved = await store.set(
        text="MINE", model_profile_id="m", reasoning_effort="high", updated_by="b"
    )
    assert resaved.updated_by == "b"
    assert resaved.updated_at is not None
    assert resaved.updated_at.replace(tzinfo=timezone.utc) > stale + timedelta(days=1)
    await engine.dispose()


@pytest.mark.asyncio
async def test_creation_assistant_routes_are_denied_without_the_relation(
    _pod_file,
) -> None:
    deps = _assistant_deps(_RoleRebac(), _AssistantStore())

    for call in (
        lambda: get_creation_assistant_settings(user=_user(), deps=deps),
        lambda: set_creation_assistant_settings(
            user=_user(), text="x", model_profile_id=None, deps=deps
        ),
        lambda: reset_creation_assistant_prompt(user=_user(), deps=deps),
    ):
        with pytest.raises(AuthorizationError):
            await call()


@pytest.mark.parametrize(
    "text",
    ["", "   ", "x" * (MAX_CREATION_ASSISTANT_PROMPT_CHARS + 1), "ok </tools>"],
)
def test_creation_assistant_request_rejects_invalid_text(text: str) -> None:
    with pytest.raises(ValueError):
        SetCreationAssistantSettingsRequest(text=text)


def test_creation_assistant_request_accepts_no_override() -> None:
    request = SetCreationAssistantSettingsRequest(model_profile_id="chat.large")
    assert (request.text, request.model_profile_id) == (None, "chat.large")
    assert request.reasoning_effort == "off"


@pytest.mark.parametrize("effort", ["max", "on", "", True])
def test_creation_assistant_request_rejects_an_unknown_effort(effort: Any) -> None:
    with pytest.raises(ValueError):
        SetCreationAssistantSettingsRequest.model_validate({"reasoning_effort": effort})


@pytest.mark.asyncio
async def test_creation_assistant_saves_any_effort_whatever_the_model_offers(
    _pod_file,
) -> None:
    # Offered-ness is the pod's clamp, never a 422: a catalog change cannot block saving.
    deps = _assistant_deps(_prompt_editor(), _AssistantStore())

    saved = await set_creation_assistant_settings(
        user=_user(),
        text=None,
        model_profile_id="chat.small",
        reasoning_effort="low",
        deps=deps,
    )

    assert saved.reasoning_effort == "low"


@pytest.mark.asyncio
async def test_put_route_forwards_the_reasoning_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from control_plane_backend.platform_prompt import api

    seen: dict[str, Any] = {}

    async def _set(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return "saved"

    monkeypatch.setattr(
        api.platform_prompt_service, "set_creation_assistant_settings", _set
    )
    request = SetCreationAssistantSettingsRequest.model_validate(
        {"model_profile_id": "chat.a", "reasoning_effort": "low"}
    )

    result = await api.put_creation_assistant_settings(request, deps=Any, user=_user())  # type: ignore[arg-type]

    assert result == "saved"
    assert (seen["model_profile_id"], seen["reasoning_effort"]) == ("chat.a", "low")


@pytest.mark.asyncio
async def test_model_options_are_chat_profiles_every_pod_serves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from control_plane_backend.platform_prompt import service
    from fred_sdk.contracts.capability import CapabilityCatalogEntry

    def _entry(
        entry_id: str,
        name: str,
        profiles: tuple[str, ...],
        thinking: tuple[str, ...] = (),
        levels: dict[str, tuple[Any, ...]] | None = None,
    ) -> Any:
        return CapabilityCatalogEntry(
            id=entry_id,
            source_id=entry_id,
            version="1",
            name=name,
            description=name,
            icon="neurology",
            kind="model",
            model_chat_profile_ids=profiles,
            model_thinking_profile_ids=thinking,
            model_reasoning_efforts=levels or {},
        )

    async def _catalog(_deps: object) -> dict[str, Any]:
        return {
            # chat.d thinks but the pod has no effort to send for it.
            "m1": _entry(
                "m1",
                "Mistral",
                ("chat.a", "chat.b", "chat.d"),
                thinking=("chat.a", "chat.d"),
                levels={"chat.d": ()},
            ),
            "m2": _entry(
                "m2",
                "GPT",
                ("chat.c", "chat.only_one_pod"),
                thinking=("chat.c",),
                levels={"chat.c": ("low", "high")},
            ),
        }

    async def _universal(_deps: object, **_kw: object) -> frozenset[str]:
        return frozenset({"chat.a", "chat.b", "chat.c", "chat.d"})

    monkeypatch.setattr(service, "aggregate_capability_catalog", _catalog)
    monkeypatch.setattr(
        service, "universally_available_chat_model_profile_ids", _universal
    )

    from control_plane_backend.product import service as product_service

    defaults = {"http://pod-1": "chat.a", "http://pod-2": "chat.a"}

    async def _pod(base_url: str) -> Any:
        return SimpleNamespace(entries=[1], default_chat_profile_id=defaults[base_url])

    monkeypatch.setattr(product_service, "_model_capabilities_for_source", _pod)
    sources = [
        SimpleNamespace(enabled=True, base_url=url)
        for url in ("http://pod-1", "http://pod-2")
    ]
    deps: Any = SimpleNamespace(
        configuration=SimpleNamespace(
            platform=SimpleNamespace(runtime_catalog_sources=sources)
        )
    )
    options, default = await service._creation_assistant_models(deps)

    assert [
        (o.profile_id, o.name, o.supports_reasoning, o.reasoning_efforts)
        for o in options
    ] == [
        ("chat.c", "GPT", True, ["low", "high"]),
        ("chat.a", "Mistral (chat.a)", True, []),
        ("chat.b", "Mistral (chat.b)", False, []),
        ("chat.d", "Mistral (chat.d)", False, []),
    ]
    assert default == "chat.a"
    defaults["http://pod-2"] = "chat.b"  # pods disagree: unknown
    assert (await service._creation_assistant_models(deps))[1] is None


_OVERRIDE_DAY = datetime(2026, 10, 8, 23, 30, tzinfo=timezone.utc)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("override", "revised_at", "expected"),
    [
        (_OVERRIDE_DAY, date(2026, 10, 9), True),
        (_OVERRIDE_DAY, date(2026, 10, 8), False),
        (_OVERRIDE_DAY, date(2026, 10, 1), False),
        (_OVERRIDE_DAY, None, False),
        (None, date(2026, 10, 9), False),
    ],
)
async def test_creation_assistant_flags_a_default_revised_after_the_override(
    _pod_file, override: datetime | None, revised_at: date | None, expected: bool
) -> None:
    stored = StoredCreationAssistantSettings(
        text="MINE" if override else None,
        model_profile_id=None,
        reasoning_effort="medium",
        updated_by="a",
        updated_at=override or _OVERRIDE_DAY,
    )
    deps = _assistant_deps(
        _prompt_editor(), _AssistantStore(stored), revised_at=revised_at
    )

    result = await get_creation_assistant_settings(user=_user(), deps=deps)

    assert result.default_revised_at == revised_at
    assert result.default_changed_since_override is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected", "expected_date"),
    [
        (
            {
                "platform_prompt": "",
                "creation_assistant_prompt": "G {language}",
                "creation_assistant_prompt_revised_at": "2026-10-08",
            },
            "G {language}",
            date(2026, 10, 8),
        ),
        ({"platform_prompt": ""}, None, None),
    ],
)
async def test_pod_fetch_reads_the_creation_assistant_default_or_none_for_older_pods(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, str],
    expected: str | None,
    expected_date: date | None,
) -> None:
    import httpx
    from control_plane_backend.platform_prompt.service import (
        fetch_pod_platform_prompt_file,
    )

    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, json=payload))
    monkeypatch.setattr(
        "control_plane_backend.platform_prompt.service.httpx.AsyncClient",
        lambda **kw: real_client(transport=transport, **kw),
    )
    deps: Any = SimpleNamespace(
        configuration=SimpleNamespace(
            platform=SimpleNamespace(
                runtime_catalog_sources=[SimpleNamespace(base_url="http://pod")]
            )
        )
    )

    pod_file = await fetch_pod_platform_prompt_file(deps)

    assert pod_file is not None
    assert pod_file.creation_assistant_prompt == expected
    assert pod_file.creation_assistant_prompt_revised_at == expected_date
