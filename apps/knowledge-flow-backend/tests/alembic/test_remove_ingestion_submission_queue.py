import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.mark.parametrize("pending", [False, True])
def test_queue_removal_preserves_pending_requests(pending, monkeypatch):
    path = Path(__file__).parents[2] / "alembic/versions/b2845a001002_remove_ingestion_submission_queue.py"
    spec = importlib.util.spec_from_file_location("remove_queue", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))
        module.downgrade()
        if pending:
            connection.execute(text("INSERT INTO kf_ingestion_submission (workflow_id, definition) VALUES ('wf', '{}')"))
            with pytest.raises(RuntimeError, match="Resolve pending"):
                module.upgrade()
            assert connection.execute(text("SELECT workflow_id FROM kf_ingestion_submission")).scalar() == "wf"
        else:
            module.upgrade()
            assert "kf_ingestion_submission" not in inspect(connection).get_table_names()
            module.downgrade()
            assert "kf_ingestion_submission" in inspect(connection).get_table_names()
    engine.dispose()
