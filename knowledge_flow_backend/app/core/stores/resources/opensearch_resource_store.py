import logging
from typing import List

from fred_core import ThreadSafeLRUCache
from opensearchpy import ConflictError, NotFoundError, OpenSearch, RequestsHttpConnection

from app.core.stores.resources.base_resource_store import (
    BaseResourceStore,
    ResourceAlreadyExistsError,
    ResourceNotFoundError,
)
from app.features.resources.structures import Resource, ResourceKind

logger = logging.getLogger(__name__)

RESOURCES_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "kind": {"type": "keyword"},  # "prompt" or "template"
            "name": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
            "description": {"type": "text"},
            "content": {"type": "text"},
            "tags": {"type": "keyword"},
            "owner_id": {"type": "keyword"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
            # Any additional fields go here
        }
    }
}


class OpenSearchResourceStore(BaseResourceStore):
    def __init__(
        self,
        host: str,
        index: str,
        username: str,
        password: str,
        secure: bool = False,
        verify_certs: bool = False,
    ):
        self.client = OpenSearch(
            host,
            http_auth=(username, password),
            use_ssl=secure,
            verify_certs=verify_certs,
            connection_class=RequestsHttpConnection,
        )
        self._cache = ThreadSafeLRUCache[str, Resource](max_size=1000)
        self.index_name = index

        if not self.client.indices.exists(index=self.index_name):
            self.client.indices.create(index=self.index_name, body=RESOURCES_INDEX_MAPPING)
            logger.info(f"[RESOURCES] OpenSearch index '{self.index_name}' created.")
        else:
            logger.info(f"[RESOURCES] OpenSearch index '{self.index_name}' already exists.")

    def list_resources_for_user(self, user: str, kind: ResourceKind) -> List[Resource]:
        try:
            q = {"query": {"bool": {"must": [{"term": {"owner_id": user}}, {"term": {"kind": kind}}]}}}
            resp = self.client.search(index=self.index_name, body=q, params={"size": 10000})
            return [Resource(**hit["_source"]) for hit in resp["hits"]["hits"]]
        except Exception as e:
            logger.error(f"[RESOURCES] Failed to list {kind}s for user '{user}': {e}")
            raise

    def get_all_resources(self, kind: ResourceKind) -> List[Resource]:
        try:
            q = {"query": {"term": {"kind": kind}}}
            resp = self.client.search(index=self.index_name, body=q, params={"size": 10000})
            return [Resource(**hit["_source"]) for hit in resp["hits"]["hits"]]
        except Exception as e:
            logger.error(f"[RESOURCES] Failed to list {kind}s: {e}")
            raise

    def get_resource_by_id(self, resource_id: str) -> Resource:
        if cached := self._cache.get(resource_id):
            return cached
        try:
            doc = self.client.get(index=self.index_name, id=resource_id)
            return Resource(**doc["_source"])
        except NotFoundError:
            raise ResourceNotFoundError(f"resource '{resource_id}' not found.")
        except Exception as e:
            logger.error(f"[RESOURCES] Failed to get resource '{resource_id}': {e}")
            raise

    def create_resource(self, resource: Resource) -> Resource:
        try:
            self.client.index(
                index=self.index_name,
                id=resource.id,
                body=resource.model_dump(mode="json"),
            )
            self._cache.set(resource.id, resource)
            logger.info(f"[RESOURCES] Created {resource.kind} '{resource.id}'")
            return resource
        except ConflictError:
            raise ResourceAlreadyExistsError(f"{resource.kind} '{resource.id}' already exists.")
        except Exception as e:
            logger.error(f"[RESOURCES] Failed to create {resource.kind} '{resource.id}': {e}")
            raise

    def update_resource(self, resource_id: str, resource: Resource) -> Resource:
        try:
            self.get_resource_by_id(resource_id)  # ensure exists
            self.client.index(
                index=self.index_name,
                id=resource_id,
                body=resource.model_dump(mode="json"),
            )
            self._cache.set(resource.id, resource)
            logger.info(f"[RESOURCES] Updated resource '{resource_id}'")
            return resource
        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[RESOURCES] Failed to update {resource.kind} '{resource_id}': {e}")
            raise

    def delete_resource(self, resource_id: str) -> None:
        self._cache.delete(resource_id)
        try:
            self.client.delete(index=self.index_name, id=resource_id)
            logger.info(f"[RESOURCES] Deleted resource '{resource_id}'")
        except NotFoundError:
            raise ResourceNotFoundError(f"resource with id '{resource_id}' not found.")
        except Exception as e:
            logger.error(f"[RESOURCES] Failed to delete resource '{resource_id}': {e}")
            raise

    def get_resources_in_tag(self, tag_id: str) -> List[Resource]:
        try:
            q = {"query": {"bool": {"must": [{"term": {"tags": tag_id}}]}}}
            resp = self.client.search(index=self.index_name, body=q, params={"size": 10000})
            if not resp["hits"]["hits"]:
                raise ResourceNotFoundError(f"No resource found for tag '{tag_id}'")
            return [Resource(**hit["_source"]) for hit in resp["hits"]["hits"]]
        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[RESOURCES] Failed to get resources for tag '{tag_id}': {e}")
            raise
