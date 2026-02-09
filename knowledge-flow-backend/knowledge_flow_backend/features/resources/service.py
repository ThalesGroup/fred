# app/features/resource/service.py

import logging
from datetime import datetime, timezone

from fred_core import Action, KeycloakUser, RebacDisabledResult, RebacReference, Relation, RelationType, authorize
from fred_core import Resource as AuthzResource
from fred_core.security.rebac.rebac_engine import ResourcePermission, TagPermission

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.resources.utils import build_resource_from_create

from .structures import Resource, ResourceCreate, ResourceKind, ResourceUpdate

logger = logging.getLogger(__name__)


def utc_now():
    return datetime.now(timezone.utc)


class ResourceService:
    def __init__(self):
        context = ApplicationContext.get_instance()
        self._resource_store = context.get_resource_store()
        self.rebac = context.get_rebac_engine()

    @authorize(Action.CREATE, AuthzResource.RESOURCES)
    async def create(self, *, library_tag_id: str, payload: ResourceCreate, user: KeycloakUser) -> Resource:
        await self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, library_tag_id)

        resource = build_resource_from_create(payload, library_tag_id, user.uid)
        res = await self._resource_store.create_resource(resource=resource)
        await self._set_tag_as_parent_in_rebac(library_tag_id, res.id)
        logger.info(f"[RESOURCES] Created resource {res.id} of kind {res.kind} for user {user.uid}")
        return res

    @authorize(Action.UPDATE, AuthzResource.RESOURCES)
    async def update(self, *, resource_id: str, payload: ResourceUpdate, user: KeycloakUser) -> Resource:
        await self.rebac.check_user_permission_or_raise(user, ResourcePermission.UPDATE, resource_id)

        res = await self._resource_store.get_resource_by_id(resource_id)
        res.content = payload.content if payload.content is not None else res.content
        res.name = payload.name if payload.name is not None else res.name
        res.description = payload.description if payload.description is not None else res.description
        res.labels = payload.labels if payload.labels is not None else res.labels
        res.updated_at = utc_now()
        updated = await self._resource_store.update_resource(resource_id=resource_id, resource=res)
        return updated

    @authorize(Action.READ, AuthzResource.RESOURCES)
    async def get(self, *, resource_id: str, user: KeycloakUser) -> Resource:
        await self.rebac.check_user_permission_or_raise(user, ResourcePermission.READ, resource_id)
        return await self._resource_store.get_resource_by_id(resource_id)

    @authorize(Action.READ, AuthzResource.RESOURCES)
    async def list_resources_by_kind(self, *, kind: ResourceKind, user: KeycloakUser) -> list[Resource]:
        authorized_resources_ref = await self.rebac.lookup_user_resources(user, ResourcePermission.READ)
        resources = await self._resource_store.get_all_resources(kind=kind)

        if isinstance(authorized_resources_ref, RebacDisabledResult):
            # rebac disabled, skip filtering
            return resources

        authorized_resources_ids = {r.id for r in authorized_resources_ref}
        return [res for res in resources if res.id in authorized_resources_ids]

    @authorize(Action.DELETE, AuthzResource.RESOURCES)
    async def delete(self, *, resource_id: str, user: KeycloakUser) -> None:
        await self.rebac.check_user_permission_or_raise(user, ResourcePermission.DELETE, resource_id)
        res = await self._resource_store.get_resource_by_id(resource_id)
        await self._resource_store.delete_resource(resource_id=resource_id)
        # Remove tag -> resource relations to keep the graph consistent
        for tag_id in res.library_tags:
            await self._remove_tag_as_parent_in_rebac(tag_id, res.id)

    @authorize(Action.UPDATE, AuthzResource.RESOURCES)
    async def add_tag_to_resource(self, user: KeycloakUser, resource_id: str, tag_id: str) -> Resource:
        await self.rebac.check_user_permission_or_raise(user, ResourcePermission.UPDATE, resource_id)
        await self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)

        res = await self._resource_store.get_resource_by_id(resource_id)
        if tag_id not in res.library_tags:
            res.library_tags.append(tag_id)
            res.updated_at = utc_now()
            res = await self._resource_store.update_resource(resource_id=res.id, resource=res)
            await self._set_tag_as_parent_in_rebac(tag_id, res.id)
        return res

    @authorize(Action.UPDATE, AuthzResource.RESOURCES)
    async def remove_tag_from_resource(self, user: KeycloakUser, resource_id: str, tag_id: str, *, delete_if_orphan: bool = True) -> None:
        await self.rebac.check_user_permission_or_raise(user, ResourcePermission.UPDATE, resource_id)
        await self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)

        res = await self._resource_store.get_resource_by_id(resource_id)
        if tag_id in res.library_tags:
            res.library_tags.remove(tag_id)
            if not res.library_tags and delete_if_orphan:
                await self._resource_store.delete_resource(resource_id=res.id)
            else:
                res.updated_at = utc_now()
                await self._resource_store.update_resource(resource_id=res.id, resource=res)
        await self._remove_tag_as_parent_in_rebac(tag_id, res.id)

    async def _set_tag_as_parent_in_rebac(self, tag_id: str, resource_id: str) -> None:
        await self.rebac.add_relation(self._get_tag_as_parent_relation(tag_id, resource_id))

    async def _remove_tag_as_parent_in_rebac(self, tag_id: str, resource_id: str) -> None:
        await self.rebac.delete_relation(self._get_tag_as_parent_relation(tag_id, resource_id))

    def _get_tag_as_parent_relation(self, tag_id: str, resource_id: str) -> Relation:
        return Relation(
            subject=RebacReference(AuthzResource.TAGS, tag_id),
            relation=RelationType.PARENT,
            resource=RebacReference(AuthzResource.RESOURCES, resource_id),
        )
