"""SpiceDB-backed implementation of the relationship authorization engine."""

from __future__ import annotations

import os
from typing import Iterable, Iterator

from authzed.api.v1 import (
    CheckPermissionRequest,
    CheckPermissionResponse,
    Client,
    Consistency,
    ObjectReference,
    ReadRelationshipsRequest,
    Relationship,
    RelationshipFilter,
    RelationshipUpdate,
    SubjectFilter,
    SubjectReference,
    WriteRelationshipsRequest,
    WriteSchemaRequest,
)
from grpcutil import insecure_bearer_token_credentials

from fred_core.security.models import Action, Resource
from fred_core.security.rebac.rebac_engine import (
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
)
from fred_core.security.rebac.schema import DEFAULT_SCHEMA

DEFAULT_TOKEN_ENV = "SPICEDB_TOKEN"


class SpiceDbRebacEngine(RebacEngine):
    """Evaluates permissions by delegating to a SpiceDB instance."""

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        token: str | None = None,
        resource_types: Iterable[Resource] | None = None,
        read_consistency: Consistency | None = None,
        write_operation: RelationshipUpdate._Operation.ValueType = RelationshipUpdate.Operation.OPERATION_TOUCH,
        schema: str | None = DEFAULT_SCHEMA,
        sync_schema_on_init: bool = True,
    ) -> None:
        resolved_endpoint = endpoint
        if not resolved_endpoint:
            raise ValueError(
                "SpiceDB endpoint must be provided via parameter or environment",
            )

        resolved_token = token or os.getenv(DEFAULT_TOKEN_ENV)
        if not resolved_token:
            raise ValueError(
                "SpiceDB token must be provided via parameter or environment",
            )

        credentials = insecure_bearer_token_credentials(resolved_token)
        self._client = Client(resolved_endpoint, credentials)

        self._resource_types: tuple[Resource, ...] = (
            tuple(resource_types) if resource_types is not None else tuple(Resource)
        )
        self._read_consistency = read_consistency
        self._write_operation = write_operation

        if schema and sync_schema_on_init:
            self.sync_schema(schema)

    def add_relation(self, relation: Relation) -> None:
        relationship = self._relationship_from_dataclass(relation)
        request = WriteRelationshipsRequest(
            updates=[
                RelationshipUpdate(
                    operation=self._write_operation,
                    relationship=relationship,
                )
            ]
        )
        self._client.WriteRelationships(request)

    def get_relations_as_subject(self, subject: RebacReference) -> list[Relation]:
        filters = [
            RelationshipFilter(
                resource_type=resource_type.value,
                optional_subject_filter=SubjectFilter(
                    subject_type=subject.type.value,
                    optional_subject_id=subject.id,
                ),
            )
            for resource_type in self._resource_types
        ]
        return list(self._read_relationships(filters))

    def get_relations_as_resource(self, resource: RebacReference) -> list[Relation]:
        filter_ = RelationshipFilter(
            resource_type=resource.type.value,
            optional_resource_id=resource.id,
        )
        return list(self._read_relationships([filter_]))

    def has_permission(
        self,
        subject: RebacReference,
        permission: Action,
        resource: RebacReference,
    ) -> bool:
        request = CheckPermissionRequest(
            resource=self._object_reference(resource),
            permission=permission.value,
            subject=SubjectReference(object=self._object_reference(subject)),
        )
        response = self._client.CheckPermission(request)
        return (
            response.permissionship
            == CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
        )

    def sync_schema(self, schema: str) -> None:
        """Create or update the SpiceDB schema definition."""

        request = WriteSchemaRequest(schema=schema)
        self._client.WriteSchema(request)

    def _read_relationships(
        self, filters: Iterable[RelationshipFilter]
    ) -> Iterator[Relation]:
        """Iterate over relationships matching the filters while de-duplicating."""
        seen: set[Relation] = set()
        for filter_ in filters:
            if self._read_consistency is not None:
                request = ReadRelationshipsRequest(
                    relationship_filter=filter_,
                    consistency=self._read_consistency,
                )
            else:
                request = ReadRelationshipsRequest(relationship_filter=filter_)
            for response in self._client.ReadRelationships(request):
                relation = self._relation_from_proto(response.relationship)
                if relation not in seen:
                    seen.add(relation)
                    yield relation

    @staticmethod
    def _object_reference(reference: RebacReference) -> ObjectReference:
        """Map a generic reference to the SpiceDB object identifier."""
        return ObjectReference(
            object_type=reference.type.value,
            object_id=reference.id,
        )

    def _relationship_from_dataclass(self, relation: Relation) -> Relationship:
        """Produce the SpiceDB relationship structure for the provided edge."""
        return Relationship(
            resource=self._object_reference(relation.resource),
            relation=relation.relation.value,
            subject=SubjectReference(
                object=self._object_reference(relation.subject),
            ),
        )

    @staticmethod
    def _relation_from_proto(relationship: Relationship) -> Relation:
        """Convert a SpiceDB relationship message back to the shared dataclass."""
        subject = SpiceDbRebacEngine._reference_from_object(relationship.subject.object)
        resource = SpiceDbRebacEngine._reference_from_object(relationship.resource)
        relation_type = RelationType(relationship.relation)
        return Relation(subject=subject, relation=relation_type, resource=resource)

    @staticmethod
    def _reference_from_object(obj: ObjectReference) -> RebacReference:
        """Re-create a reference from the SpiceDB object descriptor."""
        try:
            resource_type = Resource(obj.object_type)
        except ValueError as exc:
            raise ValueError(
                f"Unknown resource type returned by SpiceDB: {obj.object_type}",
            ) from exc
        return RebacReference(type=resource_type, id=obj.object_id)
