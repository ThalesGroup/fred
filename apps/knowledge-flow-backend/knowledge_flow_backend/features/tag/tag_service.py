# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Copyright Thales 2025
import asyncio
import logging
from datetime import datetime
from functools import cached_property
from typing import Optional
from uuid import uuid4

from fred_core import (
    FileTypeBucket,
    KeycloakUser,
    TagPermission,
    TeamPermission,
    file_type_bucket,
    is_service_agent,
)
from fred_core.common import OwnerFilter
from fred_core.security.delegation import holds_caller_role

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.core.stores.tags.base_tag_store import TagAlreadyExistsError, TagNotFoundError
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.tag.corpus_access import CorpusAccess
from knowledge_flow_backend.features.tag.structure import (
    MissingTeamIdError,
    Tag,
    TagCreate,
    TagType,
    TagUpdate,
    TagWithItemsId,
    TagWithPermissions,
)
from knowledge_flow_backend.features.tag.synchronized import refuse_if_synchronized
from knowledge_flow_backend.features.tag.tag_item_service import DocumentTagItemService

logger = logging.getLogger(__name__)

# How many documents to detach from a tag at once when deleting it. Each removal
# holds a pooled DB connection and updates the owning counter, so this bounds
# both pool usage and write contention on a single row (#2149 review). Kept
# comfortably under the production pool size rather than tuned to it.
_TAG_ITEM_DELETE_BATCH = 5


class TagService:
    """
    Service for Tag CRUD, user-scoped, with hierarchical path support.
    Corpus folders use SQL team ownership; documents reference one folder ID.
    """

    def __init__(self):
        context = ApplicationContext.get_instance()
        self._tag_store = context.get_tag_store()
        self.document_metadata_service = MetadataService()
        self.rebac = context.get_rebac_engine()

    # ---------- Public API ----------

    @cached_property
    def corpus_access(self) -> CorpusAccess:
        return CorpusAccess(self.rebac, self._tag_store)

    async def list_all_tags_for_user(
        self,
        user: KeycloakUser,
        tag_type: Optional[TagType] = None,
        path_prefix: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
        owner_filter: Optional[OwnerFilter] = None,
        team_id: Optional[str] = None,
    ) -> list[TagWithPermissions]:
        """List one team's corpus; SQL applies scope and pagination together."""
        if owner_filter == OwnerFilter.TEAM and not team_id:
            raise MissingTeamIdError("team_id is required when owner_filter is 'team'")
        resolved_team = self.corpus_access.team_id(user, team_id)
        service_read = is_service_agent(user) and not holds_caller_role(user)
        tags = await self._readable_team_folders(user, team_id, path_prefix=self._normalize_path(path_prefix), limit=limit, offset=offset)
        ids_by_tag = await self.document_metadata_service.metadata_store.document_uids_by_tags([tag.id for tag in tags])
        permissions = [TagPermission.READ]
        if not service_read and await self.rebac.has_user_permission(user, TeamPermission.CAN_UPDATE_RESOURCES, resolved_team):
            permissions.extend([TagPermission.UPDATE, TagPermission.DELETE])
        return [TagWithPermissions.from_tag_with_items(TagWithItemsId.from_tag(tag, ids_by_tag.get(tag.id, [])), permissions) for tag in tags]

    async def list_authorized_tags_ids(self, user: KeycloakUser, owner_filter: Optional[OwnerFilter], team_id: Optional[str]) -> set[str]:
        if owner_filter == OwnerFilter.TEAM and not team_id:
            raise MissingTeamIdError("team_id is required when owner_filter is 'team'")
        return {tag.id for tag in await self._readable_team_folders(user, team_id)}

    async def _readable_team_folders(self, user: KeycloakUser, team_id: str | None, *, path_prefix: str | None = None, limit: int | None = None, offset: int = 0) -> list[Tag]:
        resolved_team = self.corpus_access.team_id(user, team_id)
        return await self.corpus_access.list_readable_folders(user, resolved_team, path_prefix=path_prefix, limit=limit, offset=offset)

    async def get_corpus_type_stats(self, user: KeycloakUser, team_id: Optional[str]) -> dict[FileTypeBucket, tuple[int, int]]:
        """
        Aggregate ingested-document counts and total size per `FileTypeBucket` across
        every library (tag) the user can read in one team's corpus (FRONT-09.I usage
        cards).

        Why this exists:
        - the histogram/pie-chart cards need a per-team, per-type breakdown that no
          endpoint returns today; the running per-team storage counter
          (`_adjust_team_storage`) only tracks one running total, not a breakdown
        - computed on read rather than incrementally maintained: simpler, can't drift,
          and team libraries are bounded in size, so an on-read scan stays cheap

        How to use:
        - pass the team id (or None/"personal" for the caller's personal corpus)
        """
        tag_ids = await self.list_authorized_tags_ids(user, None, team_id)
        # Team admission above already authorized this SQL folder inventory.
        docs = await self.document_metadata_service.metadata_store.metadata_in_tags(list(tag_ids))
        totals: dict[FileTypeBucket, list[int]] = {}
        for doc in docs:
            bucket = file_type_bucket(doc.document_name)
            entry = totals.setdefault(bucket, [0, 0])
            entry[0] += 1
            entry[1] += doc.file.file_size_bytes or 0
        return {bucket: (count, size) for bucket, (count, size) in totals.items()}

    async def get_tag_for_user(self, tag_id: str, user: KeycloakUser) -> TagWithItemsId:
        tag = await self.corpus_access.get_folder(user, tag_id)
        item_ids = (await self.document_metadata_service.metadata_store.document_uids_by_tags([tag.id])).get(tag.id, [])
        return TagWithItemsId.from_tag(tag, item_ids)

    async def create_tag_for_user(self, tag_data: TagCreate, user: KeycloakUser) -> TagWithItemsId:
        owner_id = self.corpus_access.team_id(user, tag_data.team_id)
        parent = None
        if tag_data.path:
            parent = await self._tag_store.get_by_owner_type_full_path(owner_id, tag_data.type, tag_data.path)
            if parent is None:
                raise TagNotFoundError(f"Parent folder '{tag_data.path}' not found")
        if parent is not None:
            await self.corpus_access.check_folder(user, parent, write=True)
            await refuse_if_synchronized(self._tag_store, parent, user)
        else:
            await self.corpus_access.check_team(user, owner_id, write=True)
        return await self.create_tag_trusted(tag_data, owner_id=owner_id)

    async def create_tag_trusted(self, tag_data: TagCreate, *, owner_id: str) -> TagWithItemsId:
        """Persist a folder after team/source admission; no per-folder grants."""
        path = self._normalize_path(tag_data.path)
        full_path = self._compose_full_path(path, tag_data.name)
        await self._ensure_unique_full_path(owner_id=owner_id, tag_type=tag_data.type, full_path=full_path)
        now = datetime.now()
        tag = await self._tag_store.create_tag(
            Tag(id=str(uuid4()), owner_id=owner_id, created_at=now, updated_at=now, name=tag_data.name, path=path, description=tag_data.description, type=tag_data.type)
        )
        return TagWithItemsId.from_tag(tag, [])

    async def update_tag_for_user(self, tag_id: str, tag_data: TagUpdate, user: KeycloakUser) -> TagWithItemsId:
        tag = await self.corpus_access.get_folder(user, tag_id, write=True)
        # The one person-facing path that changes what a folder holds or is
        # called — adding an item, removing one, renaming, moving. Deleting the
        # folder does not come through here, and stays open on purpose.
        await refuse_if_synchronized(self._tag_store, tag, user)
        item_service = DocumentTagItemService()

        # Renaming never sends document membership from the UI snapshot.
        # Explicit membership updates retain their existing path until deletion
        # actions are cut over to the dedicated lifecycle operation.
        if tag_data.item_ids is not None:
            old_item_ids = await item_service.retrieve_items_ids_for_tag(user, tag.id)
            added_ids, removed_ids = self._compute_ids_diff(old_item_ids, tag_data.item_ids)
            await asyncio.gather(
                *(item_service.add_tag_id_to_item(user, added_id, tag_id) for added_id in added_ids),
                *(item_service.remove_tag_id_from_item(user, removed_id, tag_id) for removed_id in removed_ids),
            )

        requested_path = tag_data.path if "path" in tag_data.model_fields_set else tag.path
        if (tag.path or "") == (requested_path or ""):
            updated_tag = await self._tag_store.rename_tag(tag_id, name=tag_data.name, description=tag_data.description)
        else:
            # Existing path-changing API; no new folder move UI is introduced.
            tag.name = tag_data.name
            tag.path = requested_path
            tag.description = tag_data.description
            tag.updated_at = datetime.now()
            updated_tag = await self._tag_store.update_tag_by_id(tag_id, tag)

        # Return the up-to-date list of item ids
        item_ids = await item_service.retrieve_items_ids_for_tag(user, tag.id)
        return TagWithItemsId.from_tag(updated_tag, item_ids)

    async def delete_tag_for_user(self, tag_id: str, user: KeycloakUser) -> None:
        await self.rebac.check_user_permission_or_raise(user, TagPermission.DELETE, tag_id)

        tag = await self._tag_store.get_tag_by_id(tag_id)

        # Get all sub tags (recusrively) and the current tag
        # No UI pagination here: the default limit is a page size, and a tree
        # larger than one page would be deleted only partially, leaving orphaned
        # sub-tags and their documents' storage charged (#2149 review).
        sub_tags = await self.list_all_tags_for_user(user, tag.type, path_prefix=tag.full_path, limit=1_000_000)

        # Delete them one tag at a time, NOT with asyncio.gather. A document
        # carrying both a parent and a descendant tag is touched by two of these
        # tasks; run concurrently, each loaded its own metadata copy, removed a
        # different tag, saw a tag still remaining and saved — so the document was
        # never deleted, its storage never released, and it kept referencing tag
        # rows that both tasks then removed (#2149 review finding). The item-level
        # fan-out inside `_delete_one_tag` is untouched: those are distinct
        # documents with no shared row.
        for sub_tag in sub_tags:
            await self._delete_one_tag(sub_tag, user)

    async def _delete_one_tag(self, tag: Tag, user: KeycloakUser):
        await self.rebac.check_user_permission_or_raise(user, TagPermission.DELETE, tag.id)
        item_service = DocumentTagItemService()

        # Remove tag on all items (and delete them if they have no tag anymore).
        # Bounded batches, not one coroutine per document: each removal takes a
        # pooled DB connection and writes the owning team's counter, so an
        # unbounded gather over a large library exhausted the connection pool and
        # piled every write onto one contended row (#2149 review).
        item_ids = await item_service.retrieve_items_ids_for_tag(user, tag.id)
        for start in range(0, len(item_ids), _TAG_ITEM_DELETE_BATCH):
            batch = item_ids[start : start + _TAG_ITEM_DELETE_BATCH]
            await asyncio.gather(
                *(item_service.remove_tag_id_from_item(user, item_id, tag.id) for item_id in batch),
            )

        # Remove tag
        await self._tag_store.delete_tag_by_id(tag.id)

        # TODO: remove all relation of this tag in ReBAC

    async def update_tag_timestamp_trusted(self, tag_id: str) -> None:
        """Touch a folder after an already-authorized document write."""

        await self._tag_store.touch_tag(tag_id)

    # ---------- Internals / helpers ----------

    @staticmethod
    def _compute_ids_diff(before: list[str], after: list[str]) -> tuple[list[str], list[str]]:
        b, a = set(before), set(after)
        return list(a - b), list(b - a)

    @staticmethod
    def _normalize_path(path: Optional[str]) -> str | None:
        if path is None:
            return None
        parts = [seg.strip() for seg in path.split("/") if seg.strip()]
        return "/".join(parts) or None

    @staticmethod
    def _compose_full_path(path: Optional[str], name: str) -> str:
        return f"{path}/{name}" if path else name

    def _full_path_of(self, tag: Tag) -> str:
        return self._compose_full_path(tag.path, tag.name)

    async def _ensure_unique_full_path(
        self,
        owner_id: str,
        tag_type: TagType,
        full_path: str,
        exclude_tag_id: Optional[str] = None,
    ) -> None:
        """
        Check uniqueness of (owner_id, type, full_path). Prefer delegating to the store if it exposes a method.
        """
        existing = await self._tag_store.get_by_owner_type_full_path(owner_id, tag_type, full_path)
        if existing and existing.id != (exclude_tag_id or ""):
            if existing.type == tag_type:
                raise TagAlreadyExistsError(f"Tag '{full_path}' already exists for owner {owner_id} and type {tag_type}.")
        return
