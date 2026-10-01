import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.mark.parametrize("state", ["pending", "running", "succeeded", "failed", "cancelled"])
def test_destination_migration_requires_idle_ingestion_and_preserves_history(state, monkeypatch):
    path = Path(__file__).parents[2] / "alembic/versions/b2845a001005_ingestion_folder_admission.py"
    spec = importlib.util.spec_from_file_location("ingestion_destination", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE tag (tag_id TEXT PRIMARY KEY, name TEXT, path TEXT, owner_id TEXT)"))
            connection.execute(text("CREATE TABLE kf_task_run (task_id TEXT PRIMARY KEY, kind TEXT, state TEXT)"))
            connection.execute(text("INSERT INTO kf_task_run VALUES ('task', 'ingestion', :state)"), {"state": state})
            monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))
            if state in {"pending", "running"}:
                with pytest.raises(RuntimeError, match="Finish or manually resolve"):
                    module.upgrade()
                assert "folder_id" not in {column["name"] for column in inspect(connection).get_columns("kf_task_run")}
            else:
                module.upgrade()
                assert connection.execute(text("SELECT folder_id FROM kf_task_run")).scalar() is None
                module.downgrade()
            assert connection.execute(text("SELECT state FROM kf_task_run WHERE task_id = 'task'")).scalar() == state
    finally:
        engine.dispose()


@pytest.mark.parametrize("name,path,owner", [("Child", "Missing", "team"), ("Root", None, None), ("Old/Name", None, "team")])
def test_migration_refuses_ambiguous_hierarchy_without_rewriting_it(name, path, owner, monkeypatch):
    migration = Path(__file__).parents[2] / "alembic/versions/b2845a001005_ingestion_folder_admission.py"
    spec = importlib.util.spec_from_file_location("ingestion_destination", migration)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE kf_task_run (task_id TEXT PRIMARY KEY, kind TEXT, state TEXT)"))
            connection.execute(text("CREATE TABLE tag (tag_id TEXT PRIMARY KEY, name TEXT, path TEXT, owner_id TEXT)"))
            connection.execute(text("INSERT INTO tag VALUES ('folder', :name, :path, :owner)"), {"name": name, "path": path, "owner": owner})
            monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))
            with pytest.raises(RuntimeError, match="No hierarchy is inferred"):
                module.upgrade()
            assert "deletion_task_id" not in {column["name"] for column in inspect(connection).get_columns("tag")}
            assert connection.execute(text("SELECT name, path, owner_id FROM tag")).one() == (name, path, owner)
    finally:
        engine.dispose()
