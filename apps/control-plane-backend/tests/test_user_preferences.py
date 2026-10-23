"""Display preferences stay typed, account-scoped and merge partial updates."""

from __future__ import annotations

import pytest
from control_plane_backend.users import api as users_api
from control_plane_backend.users.preferences import (
    PatchUserPreferences,
    UserPreferencesStore,
)
from pydantic import ValidationError
from fastapi import FastAPI
from fred_core import KeycloakUser
from fred_core.security.oidc import get_current_user_before_gcu
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.asyncio
async def test_preferences_round_trip_and_account_isolation(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    store = UserPreferencesStore(control_plane_sql_engine)
    assert (await store.get("alice")).initialized is False

    saved = await store.patch(
        "alice",
        PatchUserPreferences(
            ui_theme_id="acme",
            theme_mode="dark",
            language="fr",
            sidebar_collapsed=True,
            team_sort_mode="alpha",
            agent_sort="updated_at:desc",
            trace_expanded=False,
            pane_widths={"team-wiki:rail:width": 180},
        ),
    )
    assert saved.initialized is True
    assert saved.ui_theme_id == "acme"
    assert saved.pane_widths == {"team-wiki:rail:width": 180}
    assert (await store.get("bob")).initialized is False

    await store.patch(
        "alice",
        PatchUserPreferences(
            pane_widths={
                "import-panel:width": 560,
                "inline-drawer:capability-side-panel:width": 640,
            }
        ),
    )
    reloaded = await store.get("alice")
    assert reloaded.theme_mode == "dark"
    assert reloaded.language == "fr"
    assert reloaded.team_sort_mode == "alpha"
    assert reloaded.pane_widths == {
        "team-wiki:rail:width": 180,
        "import-panel:width": 560,
        "inline-drawer:capability-side-panel:width": 640,
    }

    await store.delete("alice")
    assert (await store.get("alice")).initialized is False


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"ui_theme_id": "Cloud"},
        {"theme_mode": "midnight"},
        {"language": "de"},
        {"team_sort_mode": "random"},
        {"agent_sort": "rating"},
        {"pane_widths": {"unknown": 400}},
        {"pane_widths": {"import-panel:width": 50}},
        {"unrecognized": True},
    ],
)
def test_preference_patch_rejects_invalid_fields(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PatchUserPreferences.model_validate(payload)


@pytest.mark.asyncio
async def test_self_service_api_uses_authenticated_subject(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    store = UserPreferencesStore(control_plane_sql_engine)
    app = FastAPI()
    app.include_router(users_api.router)
    caller = "alice"
    app.dependency_overrides[get_current_user_before_gcu] = lambda: KeycloakUser(
        uid=caller, username=caller, roles=[]
    )
    app.dependency_overrides[users_api._get_user_preferences_store] = lambda: store

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        empty = await client.get("/users/me/preferences")
        assert empty.json()["initialized"] is False

        saved = await client.patch(
            "/users/me/preferences", json={"ui_theme_id": "acme", "language": "fr"}
        )
        assert saved.status_code == 200
        assert saved.json()["ui_theme_id"] == "acme"

        caller = "bob"
        other = await client.get("/users/me/preferences")
        assert other.json()["initialized"] is False
        invalid = await client.patch(
            "/users/me/preferences", json={"ui_theme_id": "Not Valid"}
        )
        assert invalid.status_code == 422
        assert (await store.get("alice")).ui_theme_id == "acme"
