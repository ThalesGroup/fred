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
    AuthorizationError,
    FileTypeBucket,
    KeycloakUser,
    RebacDisabledResult,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    TagPermission,
    TeamPermission,
    file_type_bucket,
    is_service_agent,
)
from fred_core.common import OwnerFilter
from fred_core.common.team_id import is_personal_team_id

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.core.stores.tags.base_tag_store import TagAlreadyExistsError
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.resources.service import ResourceService
from knowledge_flow_backend.features.tag.structure import (
    MissingTeamIdError,
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

# How many documents to detach from a tag at once when deleting it. Each removal
# holds a pooled DB connection and updates the owning counter, so this bounds
# both pool usage and write contention on a single row (#2149 review). Kept
# comfortably under the production pool size rather than tuned to it.
_TAG_ITEM_DELETE_BATCH = 5


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
        if team_id == "personal":
            team_id = None
            owner_filter = OwnerFilter.PERSONAL

        # 1) fetch
        tags: list[Tag] = await self._tag_store.list_all_tags()

        # Filter by permissions (if rebac is enabled)
        authorized_tag_ids = await self.resolve_authorized_tag_ids_in_rebac(user, owner_filter, team_id)
        if not isinstance(authorized_tag_ids, RebacDisabledResult):
            tags = [t for t in tags if t.id in authorized_tag_ids]

        # 2) filter by type
        if tag_type is not None:
            tags = [t for t in tags if t.type == tag_type]

        # 3) filter by path prefix (match both path itself and leaf)
        if path_prefix:
            prefix = self._normalize_path(path_prefix)
            if prefix:
                # Match on a path boundary, not a raw string prefix: plain
                # `startswith` made "/Sales" also select "/Salesforce", so
                # deleting one library silently deleted a sibling whose name
                # merely began with the same characters (#2149 review).
                tags = [t for t in tags if self._full_path_of(t) == prefix or self._full_path_of(t).startswith(prefix.rstrip("/") + "/")]

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

    async def list_authorized_tags_ids(self, user: KeycloakUser, owner_filter: Optional[OwnerFilter], team_id: Optional[str]) -> set[str]:
        if team_id == "personal" or is_personal_team_id(team_id):
            team_id = None
            owner_filter = OwnerFilter.PERSONAL
        """Convenience method to get the set of authorized tag IDs for a user. If ReBAC is disabled, return all tag IDs."""
        # todo: add a filter on tag type ?
        tag_ids = await self.resolve_authorized_tag_ids_in_rebac(user, owner_filter, team_id)
        if isinstance(tag_ids, RebacDisabledResult):
            return {t.id for t in await self._tag_store.list_all_tags()}
        return tag_ids

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
        seen_uids: set[str] = set()
        totals: dict[FileTypeBucket, list[int]] = {}
        for tag_id in tag_ids:
            docs = await self.document_metadata_service.get_document_metadata_in_tag(user, tag_id)
            for doc in docs:
                if doc.document_uid in seen_uids:
                    continue
                seen_uids.add(doc.document_uid)
                bucket = file_type_bucket(doc.document_name)
                entry = totals.setdefault(bucket, [0, 0])
                entry[0] += 1
                entry[1] += doc.file.file_size_bytes or 0
        return {bucket: (count, size) for bucket, (count, size) in totals.items()}

    async def get_tag_for_user(self, tag_id: str, user: KeycloakUser) -> TagWithItemsId:
        if is_service_agent(user):
            # EVAL-AUTH (Solution A) — extends the bypass already applied to the
            # bulk resolver (resolve_authorized_tag_ids_in_rebac) to this
            # single-tag lookup. The service_agent holds no per-user tag
            # relation, so the interactive check below always denies it.
            #
            # No team_id parameter is needed here (unlike the tabular per-uid
            # fallback, which trusts the request's own team_id): the tag's own
            # `owner_id` already tells us the team that would have to grant
            # read access, so we scope the check to that team directly rather
            # than trusting an externally supplied one. This also means a
            # personal tag (`owner_id` is a user id, not a team) safely fails
            # closed — `resolve_authorized_tag_ids_in_rebac` returns nothing
            # for a subject that isn't a real ReBAC team.
            tag = await self._tag_store.get_tag_by_id(tag_id)
            authorized_ids = await self.resolve_authorized_tag_ids_in_rebac(user, None, tag.owner_id)
            if not isinstance(authorized_ids, RebacDisabledResult) and tag_id not in authorized_ids:
                logger.warning(
                    "ReBAC authorization denied: subject=user:%s permission=%s resource=%s:%s (service_agent, team=%s)",
                    user.uid,
                    TagPermission.READ.value,
                    Resource.TAGS.value,
                    tag_id,
                    tag.owner_id,
                )
                raise AuthorizationError(user.uid, TagPermission.READ.value, Resource.TAGS)
        else:
            await self.rebac.check_user_permission_or_raise(user, TagPermission.READ, tag_id)
            tag = await self._tag_store.get_tag_by_id(tag_id)

        item_service = get_specific_tag_item_service(tag.type)
        item_ids = await item_service.retrieve_items_ids_for_tag(user, tag.id)

        return TagWithItemsId.from_tag(tag, item_ids)

    async def create_tag_for_user(self, tag_data: TagCreate, user: KeycloakUser) -> TagWithItemsId:
        team_id = tag_data.team_id
        if team_id == "personal":
            team_id = None

        # If team_id is provided, check user has permission to manage team resources
        if team_id:
            await self.rebac.check_user_team_permission_or_raise(
                user=user,
                permission=TeamPermission.CAN_UPDATE_RESOURCES,
                team_id=team_id,
            )

        # owner_id is the team or user, used for uniqueness scoping
        owner_id = team_id or user.uid

        # Normalize + uniqueness
        norm_path = self._normalize_path(tag_data.path)
        full_path = self._compose_full_path(norm_path, tag_data.name)
        await self._ensure_unique_full_path(owner_id=owner_id, tag_type=tag_data.type, full_path=full_path)

        now = datetime.now()
        tag = await self._tag_store.create_tag(
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
                ),
                actor_uid=user.uid,
            )
        else:
            await self.rebac.add_user_relation(user, RelationType.OWNER, resource_type=Resource.TAGS, resource_id=tag.id)

        # Link to parent tag in ReBAC when the new tag is nested.
        if norm_path:
            parent_tag = await self._tag_store.get_by_owner_type_full_path(owner_id=owner_id, tag_type=tag_data.type, full_path=norm_path)
            if parent_tag:
                await self.rebac.add_relation(
                    Relation(
                        subject=RebacReference(type=Resource.TAGS, id=parent_tag.id),
                        relation=RelationType.PARENT,
                        resource=RebacReference(type=Resource.TAGS, id=tag.id),
                    ),
                    actor_uid=user.uid,
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

    async def update_tag_for_user(self, tag_id: str, tag_data: TagUpdate, user: KeycloakUser) -> TagWithItemsId:
        await self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)

        tag = await self._tag_store.get_tag_by_id(tag_id)
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
        item_service = get_specific_tag_item_service(tag.type)

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
            ),
            actor_uid=user.uid,
        )

    async def unshare_tag_with_user(self, user: KeycloakUser, tag_id: str, target_id: str, target_type: Resource) -> None:
        """
        Revoke tag access previously granted to another user.
        Removes any user-tag relation regardless of the level originally assigned.
        """
        await self.rebac.check_user_permission_or_raise(user, TagPermission.SHARE, tag_id)
        for relation in list(UserTagRelation):
            await self.rebac.delete_relation(
                Relation(
                    subject=RebacReference(type=target_type, id=target_id),
                    relation=relation.to_relation(),
                    resource=RebacReference(type=Resource.TAGS, id=tag_id),
                )
            )

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

    async def update_tag_timestamp(self, tag_id: str, user: KeycloakUser) -> None:
        await self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)

        tag = await self._tag_store.get_tag_by_id(tag_id)
        tag.updated_at = datetime.now()
        await self._tag_store.update_tag_by_id(tag_id, tag)

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

    async def resolve_authorized_tag_ids_in_rebac(
        self,
        user: KeycloakUser,
        owner_filter: Optional[OwnerFilter],
        team_id: Optional[str],
    ) -> set[str] | RebacDisabledResult:
        """Return the set of tag IDs the user is allowed to see, or None if ReBAC is disabled.

        Always enforces TagPermission.READ as the security baseline.
        When an owner_filter is provided, the result is intersected with the
        owner-filtered tag IDs so only readable tags matching the filter are returned.
        """
        # EVAL-AUTH (Solution A, knowledge-flow enforcement point): the evaluation
        # worker (`service_agent`) holds no per-user tag relations, so the READ
        # baseline is empty and would zero out the result. Instead, authorize the
        # TEAM's tags directly, scoped to the request team_id (read-only). This lets a
        # RAG agent run by the worker retrieve the team's indexed corpus. Fail closed
        # without a (non-personal) team.
        if is_service_agent(user):
            if not team_id or is_personal_team_id(team_id):
                return set()
            team_ref = RebacReference(type=Resource.TEAM, id=team_id)
            owned, edited, viewed = await asyncio.gather(
                self.rebac.lookup_resources(team_ref, TagPermission.OWNER, Resource.TAGS),
                self.rebac.lookup_resources(team_ref, TagPermission.EDITOR, Resource.TAGS),
                self.rebac.lookup_resources(team_ref, TagPermission.VIEWER, Resource.TAGS),
            )
            if isinstance(owned, RebacDisabledResult) or isinstance(edited, RebacDisabledResult) or isinstance(viewed, RebacDisabledResult):
                return RebacDisabledResult()
            return {ref.id for r in (owned, edited, viewed) for ref in r}

        readable_coro = self.rebac.lookup_user_resources(user, TagPermission.READ)

        if owner_filter is None:
            readable_refs = await readable_coro
            if isinstance(readable_refs, RebacDisabledResult):
                return RebacDisabledResult()
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
        if isinstance(readable_refs, RebacDisabledResult) or isinstance(owned, RebacDisabledResult) or isinstance(edited, RebacDisabledResult) or isinstance(viewed, RebacDisabledResult):
            return RebacDisabledResult()

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
