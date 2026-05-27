from __future__ import annotations

import asyncio
import pathlib

import pytest
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture(scope="session", autouse=True)
def _setup_test_schema() -> None:
    """Ensure the test SQLite database has all ORM tables before any test runs.

    Alembic migrations are the production path; for offline unit tests we
    call create_all so the tables exist without needing a running alembic
    process.  Existing tables are left untouched (checkfirst=True default).
    """
    from fred_core.models.base import Base as FredCoreBase
    from fred_core.users.user_models import UserRow  # noqa: F401

    import control_plane_backend.models.agent_instance_models  # noqa: F401
    import control_plane_backend.models.prompt_models  # noqa: F401
    import control_plane_backend.models.purge_queue_models  # noqa: F401
    import control_plane_backend.models.session_metadata_models  # noqa: F401
    import control_plane_backend.models.team_metadata_models  # noqa: F401
    from control_plane_backend.models.base import Base as CPBase

    db_path = pathlib.Path("~/.fred/control-plane/control_plane.sqlite3").expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async def _create_all() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.run_sync(FredCoreBase.metadata.create_all)
            await conn.run_sync(CPBase.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create_all())
