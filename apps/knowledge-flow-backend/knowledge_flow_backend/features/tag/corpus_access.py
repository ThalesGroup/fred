"""Corpus authorization: persisted ownership, team rights, source-root grants.

SQL owns folder membership. ReBAC answers a permission question, never supplies
the inventory. Instantiate no permission cache here: callers can group one
request's folders by team before checking that team's permission once.
"""

from fred_core import AuthorizationError, DocumentPermission, KeycloakUser, RebacReference, RelationType, Resource, TagPermission, TeamPermission, is_service_agent
from fred_core.common.team_id import personal_team_id
from fred_core.documents.document_structures import DocumentMetadata
from fred_core.security.delegation import holds_caller_role
from fred_core.security.rebac.rebac_engine import RebacEngine

from knowledge_flow_backend.core.stores.tags.base_tag_store import BaseTagStore, TagNotFoundError
from knowledge_flow_backend.features.tag.corpus_lifecycle import CorpusBusy
from knowledge_flow_backend.features.tag.structure import Tag


class CorpusAccess:
    def __init__(self, rebac: RebacEngine, folders: BaseTagStore):
        self.rebac = rebac
        self.folders = folders

    @staticmethod
    def team_id(user: KeycloakUser, team_id: str | None) -> str:
        return personal_team_id(user.uid) if team_id in (None, "personal") else team_id

    async def check_team(self, user: KeycloakUser, team_id: str, *, write: bool = False) -> None:
        permission = TeamPermission.CAN_UPDATE_RESOURCES if write else TeamPermission.CAN_USE_TEAM_KNOWLEDGE_BASES
        if write and is_service_agent(user) and not holds_caller_role(user):
            raise AuthorizationError(user.uid, permission.value, Resource.TEAM)
        await self.rebac.check_user_permission_or_raise(user, permission, team_id)

    async def check_folders(self, user: KeycloakUser, folder_ids: list[str], *, write: bool = False) -> list[Tag]:
        folders = await self.folders.get_tags_by_ids(folder_ids)
        if {folder.id for folder in folders} != set(folder_ids):
            raise TagNotFoundError("One or more requested folders do not exist")
        if is_service_agent(user) and not holds_caller_role(user):
            roots = {(folder.owner_id, folder.path.split("/")[0] if folder.path else folder.name): folder for folder in folders}
            for folder in roots.values():
                await self.check_folder(user, folder, write=write)
        else:
            for team_id in {folder.owner_id for folder in folders}:
                await self.check_team(user, team_id, write=write)
        for folder in folders:
            self._require_available(folder, write=write)
        return folders

    @staticmethod
    def _require_available(folder: Tag, *, write: bool = False) -> None:
        if folder.deletion_task_id is not None:
            if write:
                raise CorpusBusy("The folder is being deleted")
            raise TagNotFoundError("The folder is being deleted")

    async def check_folder(self, user: KeycloakUser, folder: Tag, *, write: bool = False) -> None:
        if is_service_agent(user) and not holds_caller_role(user):
            await self.rebac.require_active_account(user.uid)
            if not await self._service_root_granted(user, folder, write=write):
                raise AuthorizationError(user.uid, TagPermission.UPDATE.value if write else TagPermission.READ.value, Resource.TAGS)
        else:
            await self.check_team(user, folder.owner_id, write=write)
        self._require_available(folder, write=write)

    async def check_documents(self, user: KeycloakUser, documents: list[DocumentMetadata], *, folder_ids: list[str] | None = None, write: bool = False) -> None:
        if any(document.kind != "corpus" or not document.tags.tag_ids for document in documents):
            raise AuthorizationError(user.uid, DocumentPermission.UPDATE.value if write else DocumentPermission.READ.value, Resource.DOCUMENTS)
        targets = set(folder_ids or []) | {document.tags.tag_ids[0] for document in documents}
        await self.check_folders(user, list(targets), write=write)

    async def check_document(self, user: KeycloakUser, document: DocumentMetadata, *, write: bool = False) -> None:
        if document.kind != "corpus" or not document.tags.tag_ids:
            raise AuthorizationError(user.uid, DocumentPermission.UPDATE.value if write else DocumentPermission.READ.value, Resource.DOCUMENTS)
        await self.get_folder(user, document.tags.tag_ids[0], write=write)

    async def _service_root_granted(self, user: KeycloakUser, folder: Tag, *, write: bool = False) -> bool:
        root = folder
        if folder.path:
            root = await self.folders.get_by_owner_type_full_path(folder.owner_id, folder.type, folder.path.split("/")[0])
            if root is None:
                return False
        if not self.rebac.enabled:
            return True
        subject = RebacReference(Resource.USER, user.uid)
        target = RebacReference(Resource.TAGS, root.id)
        if await self.rebac.has_direct_relation(subject, RelationType.EDITOR, target):
            return True
        return not write and await self.rebac.has_direct_relation(subject, RelationType.VIEWER, target)

    async def list_readable_folders(self, user: KeycloakUser, team_id: str, *, path_prefix: str | None = None, limit: int | None = None, offset: int = 0) -> list[Tag]:
        if not (is_service_agent(user) and not holds_caller_role(user)):
            await self.check_team(user, team_id)
            return await self.folders.list_by_owner(team_id, path_prefix=path_prefix, limit=limit, offset=offset)
        folders = await self.folders.list_by_owner(team_id, path_prefix=path_prefix)
        readable = await self._filter_readable_folders(user, folders)
        # Filter before pagination; a forbidden root must not consume the page.
        return readable[offset:] if limit is None else readable[offset : offset + limit]

    async def readable_folder_ids(self, user: KeycloakUser, folder_ids: set[str]) -> set[str]:
        if not folder_ids:
            return set()
        folders = await self.folders.get_tags_by_ids(list(folder_ids))
        return {folder.id for folder in await self._filter_readable_folders(user, folders)}

    async def _filter_readable_folders(self, user: KeycloakUser, folders: list[Tag]) -> list[Tag]:
        machine = is_service_agent(user) and not holds_caller_role(user)
        if machine:
            await self.rebac.require_active_account(user.uid)
        decisions: dict[tuple[str, str], bool] = {}
        readable = []
        for folder in folders:
            if folder.deletion_task_id is not None:
                continue
            root_name = (folder.path.split("/")[0] if folder.path else folder.name) if machine else ""
            key = (folder.owner_id, root_name)
            if key not in decisions:
                decisions[key] = await self._service_root_granted(user, folder) if machine else await self.rebac.has_user_permission(user, TeamPermission.CAN_USE_TEAM_KNOWLEDGE_BASES, folder.owner_id)
            if decisions[key]:
                readable.append(folder)
        return readable

    async def get_folder(self, user: KeycloakUser, folder_id: str, *, write: bool = False) -> Tag:
        folder = await self.folders.get_tag_by_id(folder_id)
        await self.check_folder(user, folder, write=write)
        return folder
