"""Make corpus membership singular and distinguish conversation attachments.

Revision ID: b2845a001004
Revises: b2845a001003
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "b2845a001004"
down_revision = "b2845a001003"
branch_labels = None
depends_on = None


def _membership(row) -> tuple[str, str | None]:
    uid = row.document_uid
    doc = row.doc or {}
    folders = row.tag_ids or []
    embedded = (doc.get("tags") or {}).get("tag_ids") or []
    if not isinstance(folders, list) or folders != embedded:
        raise RuntimeError(f"Document {uid}: SQL and JSON folder membership disagree; reconcile before upgrading.")
    if len(folders) == 1 and row.existing_folder is not None:
        return "corpus", folders[0]
    artifact = (doc.get("extensions") or {}).get("tabular_v1") or {}
    if (
        not folders
        and row.source_tag == "fast_ingest"
        and (doc.get("source") or {}).get("source_tag") == "fast_ingest"
        and (doc.get("identity") or {}).get("uploaded_by")
        and artifact.get("dataset_uid") == uid
        and row.source_library_id is None
        and row.source_key is None
    ):
        return "attachment", None
    raise RuntimeError(f"Document {uid}: ambiguous kind, missing folder or multiple folders; review before upgrading. No automatic repair is performed.")


def _batches(connection, query, uid_column):
    last_uid = None
    while True:
        page = query if last_uid is None else query.where(uid_column > last_uid)
        rows = connection.execute(page.order_by(uid_column).limit(1000)).all()
        if not rows:
            return
        yield rows
        last_uid = rows[-1].document_uid


def upgrade() -> None:
    connection = op.get_bind()
    metadata = sa.MetaData()
    documents = sa.Table("metadata", metadata, autoload_with=connection)
    folders = sa.Table("tag", metadata, autoload_with=connection)
    full_path = sa.case((sa.or_(folders.c.path.is_(None), folders.c.path == ""), folders.c.name), else_=folders.c.path + "/" + folders.c.name)
    duplicates = connection.execute(sa.select(folders.c.owner_id, full_path).group_by(folders.c.owner_id, full_path).having(sa.func.count() > 1)).first()
    if duplicates is not None:
        raise RuntimeError(f"Duplicate folder path for owner {duplicates[0]}: {duplicates[1]}; review before upgrading. No folders are merged.")
    # The JSON first element is portable across the migration's PostgreSQL and
    # SQLite fixtures; membership agreement is checked independently below.
    first_folder = documents.c.doc["tags"]["tag_ids"][0].as_string()
    query = sa.select(documents, folders.c.tag_id.label("existing_folder")).outerjoin(folders, folders.c.tag_id == first_folder)
    # Validate before altering the schema. Historical reports whose only parent
    # was in FGA are deliberately not guessed to be conversation attachments.
    for rows in _batches(connection, query, documents.c.document_uid):
        for row in rows:
            _membership(row)
    with op.batch_alter_table("metadata") as batch:
        batch.add_column(sa.Column("kind", sa.String(), nullable=True))
        batch.add_column(sa.Column("folder_id", sa.String(), nullable=True))
    updated = sa.Table("metadata", sa.MetaData(), autoload_with=connection)
    write = updated.update().where(updated.c.document_uid == sa.bindparam("uid")).values(kind=sa.bindparam("row_kind"), folder_id=sa.bindparam("row_folder"), doc=sa.bindparam("row_doc"))
    for partition in _batches(connection, query, documents.c.document_uid):
        values = []
        for row in partition:
            kind, folder_id = _membership(row)
            doc = dict(row.doc or {})
            doc.pop("kind", None)
            doc["tags"] = {key: value for key, value in (doc.get("tags") or {}).items() if key != "tag_ids"}
            values.append({"uid": row.document_uid, "row_kind": kind, "row_folder": folder_id, "row_doc": doc})
        connection.execute(write, values)
    with op.batch_alter_table("metadata") as batch:
        batch.alter_column("kind", existing_type=sa.String(), nullable=False, server_default="corpus")
        batch.create_foreign_key("fk_metadata_folder_id", "tag", ["folder_id"], ["tag_id"])
        batch.create_check_constraint("ck_metadata_kind_folder", "(kind = 'corpus' AND folder_id IS NOT NULL) OR (kind = 'attachment' AND folder_id IS NULL)")
        batch.create_index("ix_metadata_folder_id", ["folder_id"])
        batch.drop_index("idx_metadata_tag_ids_gin")
        batch.drop_column("tag_ids")
    op.create_index("uq_tag_owner_full_path", "tag", ["owner_id", sa.text("(coalesce(nullif(path, '') || '/', '') || name)")], unique=True)


def downgrade() -> None:
    connection = op.get_bind()
    op.drop_index("uq_tag_owner_full_path", table_name="tag")
    with op.batch_alter_table("metadata") as batch:
        batch.add_column(sa.Column("tag_ids", postgresql.ARRAY(sa.String()).with_variant(sa.JSON(), "sqlite"), nullable=True))
    documents = sa.Table("metadata", sa.MetaData(), autoload_with=connection)
    write = documents.update().where(documents.c.document_uid == sa.bindparam("uid")).values(tag_ids=sa.bindparam("row_folders"), doc=sa.bindparam("row_doc"))
    for partition in _batches(connection, sa.select(documents), documents.c.document_uid):
        values = []
        for row in partition:
            folders = [row.folder_id] if row.folder_id else []
            doc = dict(row.doc or {})
            doc["tags"] = {**(doc.get("tags") or {}), "tag_ids": folders}
            values.append({"uid": row.document_uid, "row_folders": folders, "row_doc": doc})
        connection.execute(write, values)
    with op.batch_alter_table("metadata") as batch:
        batch.drop_constraint("fk_metadata_folder_id", type_="foreignkey")
        batch.drop_constraint("ck_metadata_kind_folder", type_="check")
        batch.drop_index("ix_metadata_folder_id")
        batch.drop_column("folder_id")
        batch.drop_column("kind")
        batch.create_index("idx_metadata_tag_ids_gin", ["tag_ids"], postgresql_using="gin")
