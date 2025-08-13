# app/features/resource/service.py

from datetime import datetime, timezone
import logging

from app.application_context import ApplicationContext
from app.features.resources.utils import build_resource_from_create
from .structures import Resource, ResourceCreate, ResourceUpdate, ResourceKind

logger = logging.getLogger(__name__)

def utc_now():
    return datetime.now(timezone.utc)

class ResourceService:
    def __init__(self):
        context = ApplicationContext.get_instance()
        self._tag_store = context.get_tag_store()
        self._resource_store = context.get_resource_store()

    def create(self, *, library_tag_id: str, payload: ResourceCreate, user) -> Resource:
        resource = build_resource_from_create(payload, library_tag_id, user.username)
        res = self._resource_store.create_resource(resource=resource)
        logger.info(f"[RESOURCES] Created resource {res.id} of kind {res.kind} for user {user.username}")
        return res

    def update(self, *, resource_id: str, payload: ResourceUpdate, user) -> Resource:
        res = self._resource_store.get_resource_by_id(resource_id)
        res.content = payload.content if payload.content is not None else res.content
        res.name = payload.name if payload.name is not None else res.name
        res.description = payload.description if payload.description is not None else res.description
        res.labels = payload.labels if payload.labels is not None else res.labels
        res.updated_at = utc_now()
        updated = self._resource_store.update_resource(resource_id=resource_id, resource=res)
        return updated

    def get(self, *, resource_id: str, user) -> Resource:
        return self._resource_store.get_resource_by_id(resource_id)

    def list_resources_by_kind(self, *, kind: ResourceKind) -> list[Resource]:
        return self._resource_store.get_all_resources(kind=kind)

    def delete(self, *, resource_id: str) -> None:
        self._resource_store.delete_resource(resource_id=resource_id)

    # ---------- Membership helpers ----------

    def get_resource_ids_for_tag(self, kind: ResourceKind, tag_id: str) -> list[str]:
        all_resources = self._resource_store.get_all_resources(kind=kind)
        return [res.id for res in all_resources if tag_id in res.library_tags]

    def get_resources_for_tag(self, kind: ResourceKind, tag_id: str) -> list[Resource]:
        all_resources = self._resource_store.get_all_resources(kind=kind)
        return [res for res in all_resources if tag_id in res.library_tags]

    def add_tag_to_resource(self, resource_id: str, tag_id: str) -> Resource:
        res = self._resource_store.get_resource_by_id(resource_id)
        if tag_id not in res.library_tags:
            res.library_tags.append(tag_id)
            res.updated_at = utc_now()
            res = self._resource_store.update_resource(resource_id=res.id, resource=res)
        return res

    def remove_tag_from_resource(self, resource_id: str, tag_id: str, *, delete_if_orphan: bool = True) -> None:
        res = self._resource_store.get_resource_by_id(resource_id)
        if tag_id in res.library_tags:
            res.library_tags.remove(tag_id)
            if not res.library_tags and delete_if_orphan:
                self._resource_store.delete_resource(resource_id=res.id)
            else:
                res.updated_at = utc_now()
                self._resource_store.update_resource(resource_id=res.id, resource=res)

    def remove_tag_from_resources(self, kind: ResourceKind, tag_id: str) -> None:
        """Remove tag from all resources that have it; delete orphans."""
        for res in self.get_resources_for_tag(kind, tag_id):
            # This loop is smaller than scanning all resources
            if tag_id in res.library_tags:
                res.library_tags.remove(tag_id)
                if not res.library_tags:
                    self._resource_store.delete_resource(resource_id=res.id)
                else:
                    res.updated_at = utc_now()
                    self._resource_store.update_resource(resource_id=res.id, resource=res)
