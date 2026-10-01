import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.mark.parametrize("case", ["corpus", "corpus_fast_source", "attachment", "multiple", "missing", "disagree", "unknown_folder", "unknown_attachment", "duplicate_folder"])
def test_single_folder_migration_preserves_or_refuses_data(case, monkeypatch):
    path = Path(__file__).parents[2] / "alembic/versions/b2845a001004_single_folder_metadata.py"
    spec = importlib.util.spec_from_file_location("single_folder", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("PRAGMA foreign_keys=ON"))
        schema = sa.MetaData()
        tags = sa.Table("tag", schema, sa.Column("tag_id", sa.String(), primary_key=True), sa.Column("owner_id", sa.String()), sa.Column("name", sa.String()), sa.Column("path", sa.String()))
        metadata = sa.Table(
            "metadata",
            schema,
            sa.Column("document_uid", sa.String(), primary_key=True),
            sa.Column("tag_ids", sa.JSON()),
            sa.Column("source_tag", sa.String()),
            sa.Column("source_library_id", sa.String()),
            sa.Column("source_key", sa.String()),
            sa.Column("doc", sa.JSON()),
        )
        sa.Index("idx_metadata_tag_ids_gin", metadata.c.tag_ids)
        schema.create_all(connection)
        connection.execute(tags.insert(), {"tag_id": "folder", "owner_id": "team-a", "name": "Corpus"})
        if case == "duplicate_folder":
            connection.execute(tags.insert(), {"tag_id": "duplicate", "owner_id": "team-a", "name": "Corpus", "path": ""})
        folders = [] if case in {"attachment", "missing", "unknown_attachment"} else ["folder"]
        if case == "multiple":
            folders = ["folder", "another"]
        if case == "unknown_folder":
            folders = ["absent"]
        source = "fast_ingest" if case in {"attachment", "unknown_attachment", "corpus_fast_source"} else "uploads"
        doc = {"identity": {"document_uid": "doc", "uploaded_by": "alice"}, "tags": {"tag_ids": folders}, "source": {"source_tag": source}}
        if case == "attachment":
            doc["extensions"] = {"tabular_v1": {"dataset_uid": "doc"}}
        if case == "disagree":
            doc["tags"]["tag_ids"] = ["different"]
        connection.execute(metadata.insert(), {"document_uid": "doc", "tag_ids": folders, "source_tag": source, "doc": doc})
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))
        if case not in {"corpus", "corpus_fast_source", "attachment"}:
            with pytest.raises(RuntimeError, match="Duplicate folder path" if case == "duplicate_folder" else "Document doc:"):
                module.upgrade()
            assert "kind" not in {column["name"] for column in sa.inspect(connection).get_columns("metadata")}
            assert connection.execute(sa.select(metadata.c.doc)).scalar_one() == doc
        else:
            module.upgrade()
            migrated = sa.Table("metadata", sa.MetaData(), autoload_with=connection)
            row = connection.execute(sa.select(migrated)).one()
            assert row.document_uid == "doc"
            assert row.kind == ("attachment" if case == "attachment" else "corpus")
            assert row.folder_id == (None if case == "attachment" else "folder")
            assert "tag_ids" not in row.doc["tags"]
            for kind, folder in [("corpus", None), ("attachment", "folder"), ("unknown", None), ("corpus", "absent")]:
                with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                    connection.execute(migrated.insert(), {"document_uid": "invalid", "kind": kind, "folder_id": folder})
            module.downgrade()
            restored = sa.Table("metadata", sa.MetaData(), autoload_with=connection)
            row = connection.execute(sa.select(restored)).one()
            assert row.tag_ids == folders
            assert row.doc == doc
    engine.dispose()
