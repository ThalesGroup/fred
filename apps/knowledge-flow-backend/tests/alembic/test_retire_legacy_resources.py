import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.mark.parametrize("legacy", [None, "resource", "prompt", "template", "chat-context", "null"])
def test_retirement_requires_explicit_legacy_data_disposition(legacy, monkeypatch):
    path = Path(__file__).parents[2] / "alembic/versions/b2845a001003_retire_legacy_resources.py"
    spec = importlib.util.spec_from_file_location("retire_resources", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))
        module.downgrade()
        connection.execute(text("CREATE TABLE tag (tag_id TEXT PRIMARY KEY, type TEXT)"))
        connection.execute(text("INSERT INTO tag VALUES ('corpus', 'document')"))
        if legacy == "resource":
            connection.execute(text("INSERT INTO resource (resource_id) VALUES ('old')"))
        elif legacy:
            connection.execute(text("INSERT INTO tag VALUES ('old', :kind)"), {"kind": None if legacy == "null" else legacy})
        if legacy:
            with pytest.raises(RuntimeError, match="Legacy"):
                module.upgrade()
            assert "resource" in inspect(connection).get_table_names()
            if legacy == "resource":
                assert connection.execute(text("SELECT resource_id FROM resource")).scalar() == "old"
            else:
                assert connection.execute(text("SELECT count(*) FROM tag")).scalar() == 2
        else:
            module.upgrade()
            assert "resource" not in inspect(connection).get_table_names()
            module.downgrade()
            assert len(inspect(connection).get_indexes("resource")) == 3
        assert connection.execute(text("SELECT type FROM tag WHERE tag_id = 'corpus'")).scalar() == "document"
    engine.dispose()
