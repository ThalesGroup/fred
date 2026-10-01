"""Short SQL admission transactions shared by ingestion and corpus deletion.

Root folder row locks serialize admission only, never content I/O or Temporal
calls. Task rows cover uploads whose document metadata has not been written yet.
"""

from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.documents.tag_models import TagRow, tag_full_path_expression
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_flow_backend.core.stores.tags.base_tag_store import TagNotFoundError
from knowledge_flow_backend.models.task_models import KfTaskRunRow


class CorpusBusy(ValueError):
    """The requested write conflicts with admitted corpus work."""


class CorpusLifecycle:
    @staticmethod
    async def lock_folders(session: AsyncSession, folder_ids: set[str], *, deletion_task_id: str | None = None) -> list[TagRow]:
        """Lock each involved tree root, then reread and validate destinations."""
        folders = list((await session.scalars(select(TagRow).where(TagRow.tag_id.in_(folder_ids)))).all())
        if {folder.tag_id for folder in folders} != folder_ids:
            raise TagNotFoundError("One or more requested folders do not exist")
        roots = {(folder.owner_id, folder.path.split("/")[0] if folder.path else folder.name) for folder in folders}
        if not roots:
            return []
        root_rows = list(
            (
                await session.scalars(
                    select(TagRow)
                    .where(or_(*(and_(TagRow.owner_id == owner, tag_full_path_expression() == name) for owner, name in roots)))
                    .order_by(TagRow.tag_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        if {(row.owner_id, row.name) for row in root_rows} != roots:
            raise TagNotFoundError("A corpus tree root is missing")
        folders = list((await session.scalars(select(TagRow).where(TagRow.tag_id.in_(folder_ids)).execution_options(populate_existing=True))).all())
        if {folder.tag_id for folder in folders} != folder_ids:
            raise TagNotFoundError("One or more requested folders no longer exist")
        if {(folder.owner_id, folder.path.split("/")[0] if folder.path else folder.name) for folder in folders} != roots:
            raise CorpusBusy("The folder tree changed during admission. Refresh before retrying.")
        if any(folder.deletion_task_id is not None and folder.deletion_task_id != deletion_task_id for folder in folders + root_rows):
            raise CorpusBusy("The folder is being deleted")
        return folders

    @staticmethod
    async def require_no_ingestion(session: AsyncSession, folder_ids: set[str]) -> None:
        # The destination covers pre-upload admission; persisted membership also
        # covers the original folder during source refiling.
        current_documents = select(DocumentMetadataRow.document_uid).where(DocumentMetadataRow.folder_id.in_(folder_ids))
        busy = await session.scalar(
            select(KfTaskRunRow.task_id)
            .where(
                KfTaskRunRow.kind == "ingestion",
                KfTaskRunRow.state.notin_(["succeeded", "failed", "cancelled"]),
                or_(KfTaskRunRow.folder_id.in_(folder_ids), KfTaskRunRow.target["id"].as_string().in_(current_documents)),
            )
            .limit(1)
        )
        if busy is not None:
            raise CorpusBusy(f"Ingestion task {busy} is active in this folder. Wait for it to finish before deleting.")

    @staticmethod
    async def subtree(session: AsyncSession, folder: TagRow) -> list[TagRow]:
        if not folder.name:
            raise ValueError("A corpus folder must have a persisted name")
        path = f"{folder.path}/{folder.name}" if folder.path else folder.name
        return list(
            (
                await session.scalars(
                    select(TagRow).where(TagRow.owner_id == folder.owner_id, or_(tag_full_path_expression() == path, tag_full_path_expression().startswith(path + "/", autoescape=True)))
                )
            ).all()
        )

    @classmethod
    async def claim_folder_deletion(cls, session: AsyncSession, folder_id: str, task_id: str) -> list[str]:
        folders = await cls.lock_folders(session, {folder_id}, deletion_task_id=task_id)
        tree = await cls.subtree(session, folders[0])
        if any(folder.deletion_task_id not in (None, task_id) for folder in tree):
            raise CorpusBusy("A deletion is already active in this tree")
        folder_ids = {folder.tag_id for folder in tree}
        await cls.require_no_ingestion(session, folder_ids)
        await session.execute(update(TagRow).where(TagRow.tag_id.in_(folder_ids)).values(deletion_task_id=task_id))
        return sorted(folder_ids)
