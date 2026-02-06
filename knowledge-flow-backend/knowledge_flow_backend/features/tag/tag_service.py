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
from typing import Optional
from uuid import uuid4

from fred_core import (
    Action,
    KeycloakUser,
    RebacDisabledResult,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    TagPermission,
    TeamPermission,
    authorize,
)

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.core.stores.resources.base_resource_store import ResourceNotFoundError
from knowledge_flow_backend.core.stores.tags.base_tag_store import TagAlreadyExistsError
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.resources.service import ResourceService
from knowledge_flow_backend.features.tag.structure import (
    MissingTeamIdError,
    OwnerFilter,
    Tag,
    TagCreate,
    TagMemberUser,
    TagType,
    TagUpdate,
    TagWithItemsId,
    TagWithPermissions,
    UserTagRelation,
)
from knowledge_flow_backend.features.tag.tag_item_service import get_specific_tag_item_service
from knowledge_flow_backend.features.users.users_service import UserSummary, get_users_by_ids

logger = logging.getLogger(__name__)


class TagService:
    """
    Service for Tag CRUD, user-scoped, with hierarchical path support.
    Documents & prompts still link by tag *id* (no change to metadata schema).
    """

    def __init__(self):
        context = ApplicationContext.get_instance()
        self._tag_store = context.get_tag_store()
        self.document_metadata_service = MetadataService()
        self.resource_service = ResourceService()  # For templates, if needed
        self.rebac = context.get_rebac_engine()

    # ---------- Public API ----------

    @authorize(Action.READ, Resource.TAGS)
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
        """
        List user tags, optionally filtered by type and hierarchical prefix (e.g. 'Sales' or 'Sales/HR').
        Pagination included.

        owner_filter controls which tags are returned:
        - None: all tags the user can read (default, current behavior)
        - PERSONAL: only tags where the user is directly owner/editor/viewer (not via team)
        - TEAM: only tags owned by the specified team (team_id required)
        """
        # 1) fetch
        tags: list[Tag] = self._tag_store.list_all_tags()

        # Filter by permission / ownership
        authorized_tag_ids = await self._resolve_authorized_tag_ids(user, owner_filter, team_id)
        if authorized_tag_ids is not None:
            tags = [t for t in tags if t.id in authorized_tag_ids]

        # 2) filter by type
        if tag_type is not None:
            tags = [t for t in tags if t.type == tag_type]

        # 3) filter by path prefix (match both path itself and leaf)
        if path_prefix:
            prefix = self._normalize_path(path_prefix)
            if prefix:
                tags = [t for t in tags if self._full_path_of(t).startswith(prefix)]

        # 4) stable sort by full_path (optional but nice for UI determinism)
        tags.sort(key=lambda t: self._full_path_of(t).lower())

        # 5) paginate
        sliced = tags[offset : offset + limit]

        # 6) attach item ids
        tags_with_items: list[TagWithItemsId] = []
        for tag in sliced:
            item_service = get_specific_tag_item_service(tag.type)
            item_ids = await item_service.retrieve_items_ids_for_tag(user, tag.id)
            tags_with_items.append(TagWithItemsId.from_tag(tag, item_ids))

        # 7) batch-resolve permissions for all returned tags
        tag_ids = {t.id for t in tags_with_items}
        permissions_map = await self._get_tag_permissions_for_list(user, tag_ids)

        tags_with_perm = [TagWithPermissions.from_tag_with_items(t, permissions_map.get(t.id, [])) for t in tags_with_items]

        logger.info(
            "[TAGS] list_all_tags_for_user user=%s type=%s owner_filter=%s returned=%d tags=%s",
            user.uid,
            tag_type,
            owner_filter,
            len(tags_with_perm),
            [t.id for t in tags_with_perm],
        )
        return tags_with_perm

    @authorize(Action.READ, Resource.TAGS)
    async def get_tag_for_user(self, tag_id: str, user: KeycloakUser) -> TagWithItemsId:
        await self.rebac.check_user_permission_or_raise(user, TagPermission.READ, tag_id)

        tag = self._tag_store.get_tag_by_id(tag_id)
        item_service = get_specific_tag_item_service(tag.type)
        item_ids = await item_service.retrieve_items_ids_for_tag(user, tag.id)

        return TagWithItemsId.from_tag(tag, item_ids)

    @authorize(Action.CREATE, Resource.TAGS)
    async def create_tag_for_user(self, tag_data: TagCreate, user: KeycloakUser) -> TagWithItemsId:
        team_id = tag_data.team_id

        # If team_id is provided, check user has permission to manage team resources
        if team_id:
            await self.rebac.check_user_permission_or_raise(user, TeamPermission.CAN_UPDATE_RESOURCES, team_id)

        # owner_id is the team or user, used for uniqueness scoping
        owner_id = team_id or user.uid

        # Normalize + uniqueness
        norm_path = self._normalize_path(tag_data.path)
        full_path = self._compose_full_path(norm_path, tag_data.name)
        self._ensure_unique_full_path(owner_id=owner_id, tag_type=tag_data.type, full_path=full_path)

        now = datetime.now()
        tag = self._tag_store.create_tag(
            Tag(
                id=str(uuid4()),
                owner_id=owner_id,
                created_at=now,
                updated_at=now,
                name=tag_data.name,
                path=norm_path,
                description=tag_data.description,
                type=tag_data.type,
            )
        )

        # Create ReBAC ownership: team owns the tag, or user owns the tag
        if team_id:
            await self.rebac.add_relation(
                Relation(
                    subject=RebacReference(type=Resource.TEAM, id=team_id),
                    relation=RelationType.OWNER,
                    resource=RebacReference(type=Resource.TAGS, id=tag.id),
                )
            )
        else:
            await self.rebac.add_user_relation(user, RelationType.OWNER, resource_type=Resource.TAGS, resource_id=tag.id)

        # Link to parent tag in ReBAC when the new tag is nested.
        if norm_path:
            parent_tag = self._tag_store.get_by_owner_type_full_path(owner_id=owner_id, tag_type=tag_data.type, full_path=norm_path)
            if parent_tag:
                await self.rebac.add_relation(
                    Relation(
                        subject=RebacReference(type=Resource.TAGS, id=parent_tag.id),
                        relation=RelationType.PARENT,
                        resource=RebacReference(type=Resource.TAGS, id=tag.id),
                    )
                )
            else:
                logger.warning(
                    "[TAGS] Parent tag not found for full_path=%s (owner=%s, type=%s) during creation of %s",
                    norm_path,
                    owner_id,
                    tag_data.type,
                    tag.id,
                )

        return TagWithItemsId.from_tag(tag, [])

    @authorize(Action.UPDATE, Resource.TAGS)
    async def update_tag_for_user(self, tag_id: str, tag_data: TagUpdate, user: KeycloakUser) -> TagWithItemsId:
        await self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)

        tag = self._tag_store.get_tag_by_id(tag_id)
        item_service = get_specific_tag_item_service(tag.type)

        # Add / remove changed item ids
        old_item_ids = await item_service.retrieve_items_ids_for_tag(user, tag.id)
        added_ids, removed_ids = self._compute_ids_diff(old_item_ids, tag_data.item_ids)

        await asyncio.gather(
            *(item_service.add_tag_id_to_item(user, added_id, tag_id) for added_id in added_ids),
            *(item_service.remove_tag_id_from_item(user, removed_id, tag_id) for removed_id in removed_ids),
        )

        # Update tag
        tag.updated_at = datetime.now()
        updated_tag = self._tag_store.update_tag_by_id(tag_id, tag)

        # Return the up-to-date list of item ids
        item_ids = await item_service.retrieve_items_ids_for_tag(user, tag.id)
        return TagWithItemsId.from_tag(updated_tag, item_ids)

    @authorize(Action.DELETE, Resource.TAGS)
    async def delete_tag_for_user(self, tag_id: str, user: KeycloakUser) -> None:
        await self.rebac.check_user_permission_or_raise(user, TagPermission.DELETE, tag_id)

        tag = self._tag_store.get_tag_by_id(tag_id)

        # Get all sub tags (recusrively) and the current tag
        sub_tags = await self.list_all_tags_for_user(user, tag.type, path_prefix=tag.full_path)

        # Delete all of them
        await asyncio.gather(*(self._delete_one_tag(sub_tag, user) for sub_tag in sub_tags))

    async def _delete_one_tag(self, tag: Tag, user: KeycloakUser):
        await self.rebac.check_user_permission_or_raise(user, TagPermission.DELETE, tag.id)
        item_service = get_specific_tag_item_service(tag.type)

        # Remove tag on all items (and delete them if they have no tag anymore)
        item_ids = await item_service.retrieve_items_ids_for_tag(user, tag.id)
        await asyncio.gather(
            *(item_service.remove_tag_id_from_item(user, item_id, tag.id) for item_id in item_ids),
        )

        # Remove tag
        self._tag_store.delete_tag_by_id(tag.id)

        # TODO: remove all relation of this tag in ReBAC

    async def share_tag_with_user(
        self,
        user: KeycloakUser,
        tag_id: str,
        target_id: str,
        target_type: Resource,
        relation: UserTagRelation,
    ) -> None:
        """
        Share a tag with another user by adding a relation in the ReBAC engine.
        """
        await self.rebac.check_user_permission_or_raise(user, TagPermission.SHARE, tag_id)
        await self.rebac.add_relation(
            Relation(
                subject=RebacReference(type=target_type, id=target_id),
                relation=relation.to_relation(),
                resource=RebacReference(type=Resource.TAGS, id=tag_id),
            )
        )

    async def unshare_tag_with_user(self, user: KeycloakUser, tag_id: str, target_id: str, target_type: Resource) -> None:
        """
        Revoke tag access previously granted to another user.
        Removes any user-tag relation regardless of the level originally assigned.
        """
        await self.rebac.check_user_permission_or_raise(user, TagPermission.SHARE, tag_id)
        for relation in UserTagRelation:
            await self.rebac.delete_relation(
                Relation(
                    subject=RebacReference(type=target_type, id=target_id),
                    relation=relation.to_relation(),
                    resource=RebacReference(type=Resource.TAGS, id=tag_id),
                )
            )

    @authorize(Action.READ, Resource.TAGS)
    async def list_tag_members(self, tag_id: str, user: KeycloakUser) -> list[TagMemberUser]:
        """
        List users who have access to the tag along with their relation level.
        """
        await self.rebac.check_user_permission_or_raise(user, TagPermission.READ, tag_id)

        # Fetch user relations
        user_relations = await self._get_tag_members_by_type(tag_id, Resource.USER)

        # Fetch user summaries
        user_summaries = await get_users_by_ids(user_relations.keys())

        # Compose result
        users: list[TagMemberUser] = []
        for user_id, relation in user_relations.items():
            summary = user_summaries.get(user_id) or UserSummary(id=user_id)
            users.append(TagMemberUser(relation=relation, user=summary))

        return users

    @authorize(Action.UPDATE, Resource.TAGS)
    async def update_tag_timestamp(self, tag_id: str, user: KeycloakUser) -> None:
        await self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)

        tag = self._tag_store.get_tag_by_id(tag_id)
        tag.updated_at = datetime.now()
        self._tag_store.update_tag_by_id(tag_id, tag)

    @authorize(Action.UPDATE, Resource.TAGS)
    async def backfill_rebac_relations(self, user: KeycloakUser) -> dict:
        """
        Recreate missing ReBAC relations for existing tags and their documents.
        Intended for migrations when enabling ReBAC on an existing instance.
        """
        # If ReBAC is disabled, no-op but stay consistent with other calls.
        if getattr(self.rebac, "enabled", True) is False:
            return {
                "rebac_enabled": False,
                "tags_seen": 0,
                "documents_seen": 0,
                "resources_seen": 0,
                "tag_owner_relations_created": 0,
                "tag_parent_relations_created": 0,
            }

        tags = self._tag_store.list_all_tags()
        tag_owner_relations_created = 0
        tag_parent_relations_created = 0
        documents_seen = 0
        resources_seen = 0

        # Access underlying stores directly to avoid permission-filtered queries during migration.
        metadata_store = self.document_metadata_service.metadata_store
        resource_store = self.resource_service._resource_store

        for tag in tags:
            try:
                await self.rebac.add_relation(
                    Relation(
                        subject=RebacReference(type=Resource.USER, id=tag.owner_id),
                        relation=RelationType.OWNER,
                        resource=RebacReference(type=Resource.TAGS, id=tag.id),
                    )
                )
                tag_owner_relations_created += 1
            except Exception as exc:
                logger.warning("Failed to backfill owner relation for tag %s: %s", tag.id, exc)

            # Tags drive parent relations depending on their type (documents vs other resources)
            if tag.type == TagType.DOCUMENT:
                try:
                    docs = metadata_store.get_metadata_in_tag(tag.id)
                except Exception as exc:
                    logger.warning("Failed to list documents for tag %s during backfill: %s", tag.id, exc)
                    continue

                for doc in docs:
                    doc_uid = getattr(doc, "document_uid", None) or getattr(doc.identity, "document_uid", None)
                    if not doc_uid:
                        continue
                    documents_seen += 1
                    try:
                        await self.rebac.add_relation(
                            Relation(
                                subject=RebacReference(type=Resource.TAGS, id=tag.id),
                                relation=RelationType.PARENT,
                                resource=RebacReference(type=Resource.DOCUMENTS, id=doc_uid),
                            )
                        )
                        tag_parent_relations_created += 1
                    except Exception as exc:
                        logger.warning("Failed to backfill tag->document relation for tag %s doc %s: %s", tag.id, doc_uid, exc)
            elif tag.type == TagType.CHAT_CONTEXT:
                try:
                    resources = resource_store.get_resources_in_tag(tag.id)
                except ResourceNotFoundError:
                    resources = []
                except Exception as exc:
                    logger.warning("Failed to list resources for tag %s during backfill: %s", tag.id, exc)
                    continue

                for res in resources:
                    resources_seen += 1
                    try:
                        await self.rebac.add_relation(
                            Relation(
                                subject=RebacReference(type=Resource.TAGS, id=tag.id),
                                relation=RelationType.PARENT,
                                resource=RebacReference(type=Resource.RESOURCES, id=res.id),
                            )
                        )
                        tag_parent_relations_created += 1
                    except Exception as exc:
                        logger.warning("Failed to backfill tag->resource relation for tag %s resource %s: %s", tag.id, res.id, exc)
            else:
                # No parent relations to backfill for other tag types.
                continue

        return {
            "rebac_enabled": True,
            "tags_seen": len(tags),
            "documents_seen": documents_seen,
            "resources_seen": resources_seen,
            "tag_owner_relations_created": tag_owner_relations_created,
            "tag_parent_relations_created": tag_parent_relations_created,
        }

    # ---------- Internals / helpers ----------

    # Permissions that are actual ReBAC relations (owner/editor/viewer),
    # not action-based permissions. We exclude them from the batch permission
    # check since they are not useful for frontend UI gating.
    _RELATION_PERMISSIONS: set[TagPermission] = {perm for perm in TagPermission if perm.value in {rt.value for rt in RelationType}}

    async def _get_tag_permissions_for_list(
        self,
        user: KeycloakUser,
        tag_ids: set[str],
    ) -> dict[str, list[TagPermission]]:
        """Batch-resolve action permissions for multiple tags using lookup_resources.

        Uses one lookup_resources call per permission type (O(permissions), not O(tags × permissions)).
        """
        if not tag_ids:
            return {}

        action_permissions = [p for p in TagPermission if p not in self._RELATION_PERMISSIONS]

        results = await asyncio.gather(*[self.rebac.lookup_user_resources(user, perm) for perm in action_permissions])

        perm_map: dict[str, list[TagPermission]] = {tid: [] for tid in tag_ids}
        for perm, authorized_refs in zip(action_permissions, results):
            if isinstance(authorized_refs, RebacDisabledResult):
                # ReBAC disabled: grant all action permissions to every tag
                for tid in tag_ids:
                    perm_map[tid] = list(action_permissions)
                return perm_map
            authorized_ids = {ref.id for ref in authorized_refs}
            for tid in tag_ids & authorized_ids:
                perm_map[tid].append(perm)

        return perm_map

    async def _resolve_authorized_tag_ids(
        self,
        user: KeycloakUser,
        owner_filter: Optional[OwnerFilter],
        team_id: Optional[str],
    ) -> set[str] | None:
        """Return the set of tag IDs the user is allowed to see, or None if ReBAC is disabled.

        Always enforces TagPermission.READ as the security baseline.
        When an owner_filter is provided, the result is intersected with the
        owner-filtered tag IDs so only readable tags matching the filter are returned.
        """
        readable_coro = self.rebac.lookup_user_resources(user, TagPermission.READ)

        if owner_filter is None:
            readable_refs = await readable_coro
            if isinstance(readable_refs, RebacDisabledResult):
                return None
            return {ref.id for ref in readable_refs}

        # Determine the subject reference based on the filter
        if owner_filter == OwnerFilter.TEAM:
            if not team_id:
                raise MissingTeamIdError("team_id is required when owner_filter is 'team'")
            subject_ref = RebacReference(type=Resource.TEAM, id=team_id)
        else:
            subject_ref = RebacReference(type=Resource.USER, id=user.uid)

        # Run all lookups in parallel: security baseline + owner-filtered lookups
        readable_refs, owned, edited, viewed = await asyncio.gather(
            readable_coro,
            self.rebac.lookup_resources(subject_ref, TagPermission.OWNER, Resource.TAGS),
            self.rebac.lookup_resources(subject_ref, TagPermission.EDITOR, Resource.TAGS),
            self.rebac.lookup_resources(subject_ref, TagPermission.VIEWER, Resource.TAGS),
        )
        if isinstance(readable_refs, RebacDisabledResult) or any(isinstance(r, RebacDisabledResult) for r in (owned, edited, viewed)):
            return None

        readable_ids = {ref.id for ref in readable_refs}
        filtered_ids = {ref.id for r in (owned, edited, viewed) for ref in r}
        return readable_ids & filtered_ids

    async def _get_tag_members_by_type(self, tag_id: str, subject_type: Resource) -> dict[str, UserTagRelation]:
        tag_reference = RebacReference(type=Resource.TAGS, id=tag_id)
        relation_priority = {
            UserTagRelation.OWNER: 0,
            UserTagRelation.EDITOR: 1,
            UserTagRelation.VIEWER: 2,
        }
        members: dict[str, UserTagRelation] = {}

        for relation in (
            UserTagRelation.OWNER,
            UserTagRelation.EDITOR,
            UserTagRelation.VIEWER,
        ):
            subjects = await self.rebac.lookup_subjects(tag_reference, relation.to_relation(), subject_type)
            if isinstance(subjects, RebacDisabledResult):
                return {}

            for subject in subjects:
                current = members.get(subject.id)
                if current is None or relation_priority[relation] < relation_priority[current]:
                    members[subject.id] = relation

        return members

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

    def _ensure_unique_full_path(
        self,
        owner_id: str,
        tag_type: TagType,
        full_path: str,
        exclude_tag_id: Optional[str] = None,
    ) -> None:
        """
        Check uniqueness of (owner_id, type, full_path). Prefer delegating to the store if it exposes a method.
        """
        existing = self._tag_store.get_by_owner_type_full_path(owner_id, tag_type, full_path)
        if existing and existing.id != (exclude_tag_id or ""):
            if existing.type == tag_type:
                raise TagAlreadyExistsError(f"Tag '{full_path}' already exists for owner {owner_id} and type {tag_type}.")
        return
