from __future__ import annotations

import asyncio
import pathlib

import pytest
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture(scope="session", autouse=True)
def _setup_test_schema() -> None:
    """Ensure the test SQLite database has a fresh schema before any test runs.

    Alembic migrations are the production path; for offline unit tests we
    drop and recreate all tables so the schema always matches the current ORM
    models, even when new columns are added between test runs.
    """
    import control_plane_backend.models.agent_instance_models  # noqa: F401
    import control_plane_backend.models.model_reasoning_models  # noqa: F401
    import control_plane_backend.models.prompt_models  # noqa: F401
    import control_plane_backend.models.purge_queue_models  # noqa: F401
    import control_plane_backend.models.session_metadata_models  # noqa: F401
    import control_plane_backend.models.task_models  # noqa: F401
    from control_plane_backend.models.base import Base as CPBase
    from fred_core.models.base import Base as FredCoreBase
    from fred_core.teams import TeamMetadataRow  # noqa: F401
    from fred_core.users.user_models import UserRow  # noqa: F401

    db_path = pathlib.Path(
        "~/.fred/control-plane/control_plane_test.sqlite3"
    ).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async def _create_all() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.run_sync(FredCoreBase.metadata.drop_all)
            await conn.run_sync(CPBase.metadata.drop_all)
            await conn.run_sync(FredCoreBase.metadata.create_all)
            await conn.run_sync(CPBase.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create_all())


@pytest.fixture(autouse=True)
def _clear_module_level_caches() -> None:
    """Reset the #2148/#2181 relation/user-summary caches before every test.

    `control_plane_backend.teams.service._TEAM_RELATIONS_CACHE`,
    `control_plane_backend.capabilities.enablement._CAPABILITY_RELATIONS_CACHE`,
    and `control_plane_backend.users.service._USER_SUMMARY_CACHE` are
    module-level singletons with a real TTL (45s / 5min) — without this, a
    test asserting a real fan-out call count (e.g.
    `test_teams_bulk_membership_call_count.py`,
    `test_capability_relations_cache_2181.py`) could silently pass fewer calls
    than expected because an earlier test in the same session already warmed
    the cache for an overlapping team/capability id (both use predictable ids
    like `team-0`, `corp_drive`, ...).
    """
    from control_plane_backend.capabilities import enablement as capabilities_enablement
    from control_plane_backend.teams import service as teams_service
    from control_plane_backend.users import service as users_service

    teams_service._TEAM_RELATIONS_CACHE.clear()
    capabilities_enablement._CAPABILITY_RELATIONS_CACHE.clear()
    capabilities_enablement._CAPABILITY_RELATIONS_LAST_INVALIDATED.clear()
    users_service._USER_SUMMARY_CACHE.clear()
