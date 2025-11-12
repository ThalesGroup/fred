# app/features/resource/service.py

import logging
from datetime import datetime, timezone

from fred_core import Action, KeycloakUser, authorize
from fred_core import Resource as AuthzResource

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

    @authorize(Action.CREATE, AuthzResource.RESOURCES)
    def create(self, *, library_tag_id: str, payload: ResourceCreate, user: KeycloakUser) -> Resource:
        resource = build_resource_from_create(payload, library_tag_id, user.uid)
        res = self._resource_store.create_resource(resource=resource)
        logger.info(f"[RESOURCES] Created resource {res.id} of kind {res.kind} for user {user.uid}")
        return res

    @authorize(Action.UPDATE, AuthzResource.RESOURCES)
    def update(self, *, resource_id: str, payload: ResourceUpdate, user: KeycloakUser) -> Resource:
        res = self._resource_store.get_resource_by_id(resource_id)
        res.content = payload.content if payload.content is not None else res.content
        res.name = payload.name if payload.name is not None else res.name
        res.description = payload.description if payload.description is not None else res.description
        res.labels = payload.labels if payload.labels is not None else res.labels
        res.updated_at = utc_now()
        updated = self._resource_store.update_resource(resource_id=resource_id, resource=res)
        return updated

    @authorize(Action.READ, AuthzResource.RESOURCES)
    def get(self, *, resource_id: str, user: KeycloakUser) -> Resource:
        return self._resource_store.get_resource_by_id(resource_id)

    @authorize(Action.READ, AuthzResource.RESOURCES)
    def list_resources_by_kind(self, *, kind: ResourceKind, user: KeycloakUser) -> list[Resource]:
        return self._resource_store.get_all_resources(kind=kind)

    @authorize(Action.DELETE, AuthzResource.RESOURCES)
    def delete(self, *, resource_id: str, user: KeycloakUser) -> None:
        self._resource_store.delete_resource(resource_id=resource_id)

    @authorize(Action.UPDATE, AuthzResource.RESOURCES)
    def add_tag_to_resource(self, user: KeycloakUser, resource_id: str, tag_id: str) -> Resource:
        res = self._resource_store.get_resource_by_id(resource_id)
        if tag_id not in res.library_tags:
            res.library_tags.append(tag_id)
            res.updated_at = utc_now()
            res = self._resource_store.update_resource(resource_id=res.id, resource=res)
        return res

    @authorize(Action.UPDATE, AuthzResource.RESOURCES)
    def remove_tag_from_resource(self, user: KeycloakUser, resource_id: str, tag_id: str, *, delete_if_orphan: bool = True) -> None:
        res = self._resource_store.get_resource_by_id(resource_id)
        if tag_id in res.library_tags:
            res.library_tags.remove(tag_id)
            if not res.library_tags and delete_if_orphan:
                self._resource_store.delete_resource(resource_id=res.id)
            else:
                res.updated_at = utc_now()
                self._resource_store.update_resource(resource_id=res.id, resource=res)
