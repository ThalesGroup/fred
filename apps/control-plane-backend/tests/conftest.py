from __future__ import annotations

import asyncio
import pathlib
import shutil
import tempfile

import pytest
import yaml
from sqlalchemy.ext.asyncio import create_async_engine

_CONFIG_SOURCE = (
    pathlib.Path(__file__).resolve().parents[1] / "config" / "configuration_test.yaml"
)

# Set by pytest_configure before collection; read by the fixtures below.
_RUN_ROOT: pathlib.Path | None = None
_PRE_EXISTING_DATABASES: dict[pathlib.Path, tuple[int, int]] = {}


def _run_root() -> pathlib.Path:
    if _RUN_ROOT is None:
        raise RuntimeError("Test isolation root was not initialised.")
    return _RUN_ROOT


def _configured_database_path() -> pathlib.Path:
    """The database the test configuration selects, resolved as the app does.

    Read from that file rather than repeated here, so the schema this fixture
    resets and the database those tests open cannot drift apart.
    """
    settings = yaml.safe_load(_CONFIG_SOURCE.read_text())
    raw = settings["storage"]["postgres"]["sqlite_path"]
    return pathlib.Path(raw).expanduser().resolve()


def _run_database_path() -> pathlib.Path:
    return _run_root() / "control_plane.sqlite3"


def _home_database_dir() -> pathlib.Path:
    """Directory holding a developer's own databases, which tests never touch."""
    return pathlib.Path("~/.fred/control-plane").expanduser()


def pytest_configure(config: pytest.Config) -> None:
    """Give the run its own root, and record the databases it must not touch.

    Installed before collection because the schema fixture drops and recreates
    every table in the database it is pointed at.
    """
    global _RUN_ROOT
    _RUN_ROOT = pathlib.Path(tempfile.mkdtemp(prefix="control-plane-tests-"))

    home_dir = _home_database_dir()
    if home_dir.is_dir():
        for existing in home_dir.glob("*.sqlite3"):
            stat = existing.stat()
            _PRE_EXISTING_DATABASES[existing] = (stat.st_mtime_ns, stat.st_size)


def pytest_unconfigure(config: pytest.Config) -> None:
    if _RUN_ROOT is not None:
        shutil.rmtree(_RUN_ROOT, ignore_errors=True)


@pytest.fixture(scope="session")
def isolated_run_root() -> pathlib.Path:
    """Temporary root owned by this run; removed when the session ends."""
    return _run_root()


@pytest.fixture(scope="session")
def configured_database_path() -> pathlib.Path:
    """The database the test configuration selects; reset once per session."""
    return _configured_database_path()


@pytest.fixture(scope="session")
def isolated_database_path() -> pathlib.Path:
    """A per-run database for tests that must not share session state."""
    return _run_database_path()


@pytest.fixture(scope="session")
def isolated_config_path() -> pathlib.Path:
    """A test configuration whose storage paths stay under the run root.

    Opt in per test with `monkeypatch.setenv("CONFIG_FILE", ...)`; the process
    default is left alone because tests resolve several different configurations.
    """
    settings = yaml.safe_load(_CONFIG_SOURCE.read_text())
    settings["storage"]["postgres"]["sqlite_path"] = str(_run_database_path())
    settings["storage"]["content_storage"]["root_path"] = str(
        _run_root() / "content-storage"
    )
    generated = _run_root() / "configuration_test.yaml"
    generated.write_text(yaml.safe_dump(settings, sort_keys=False))
    return generated


@pytest.fixture(scope="session")
def pre_existing_databases() -> dict[pathlib.Path, tuple[int, int]]:
    """Modification time and size of each developer database seen at start-up."""
    return dict(_PRE_EXISTING_DATABASES)


@pytest.fixture(scope="session", autouse=True)
def _setup_test_schema() -> None:
    """Ensure the run's database has a fresh schema before any test runs.

    Alembic migrations are the production path; for offline unit tests we
    drop and recreate all tables so the schema always matches the current ORM
    models, even when new columns are added between test runs.
    """
    import control_plane_backend.models.agent_instance_models  # noqa: F401
    import control_plane_backend.models.model_reasoning_models  # noqa: F401
    import control_plane_backend.models.platform_model_binding_models  # noqa: F401
    import control_plane_backend.models.prompt_models  # noqa: F401
    import control_plane_backend.models.purge_queue_models  # noqa: F401
    import control_plane_backend.models.routing_policy_models  # noqa: F401
    import control_plane_backend.models.session_metadata_models  # noqa: F401
    import control_plane_backend.models.task_models  # noqa: F401
    from control_plane_backend.models.base import Base as CPBase
    from fred_core.models.base import Base as FredCoreBase
    from fred_core.teams import TeamMetadataRow  # noqa: F401
    from fred_core.users.user_models import UserRow  # noqa: F401

    db_path = _configured_database_path()
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
    teams_service._TEAM_RELATIONS_INVALIDATION_TICKET.clear()
    capabilities_enablement._CAPABILITY_RELATIONS_CACHE.clear()
    capabilities_enablement._CAPABILITY_RELATIONS_INVALIDATION_TICKET.clear()
    users_service._USER_SUMMARY_CACHE.clear()


class _NoPublishedKnowledgeBases:
    """Knowledge Base store stub: nothing published."""

    async def list_all(self) -> list:
        return []


def no_knowledge_base_store() -> _NoPublishedKnowledgeBases:
    """`deps.get_knowledge_base_definition_store` for capability-catalog tests.

    `aggregate_capability_catalog` projects published Knowledge Base
    definitions alongside applications, so any deps double it is handed needs
    this accessor. Tests asserting on the catalog's other kinds publish none.
    """

    return _NoPublishedKnowledgeBases()
