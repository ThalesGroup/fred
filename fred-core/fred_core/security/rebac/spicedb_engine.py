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
    ZedToken,
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

DEFAULT_TOKEN_ENV = "SPICEDB_TOKEN"  # nosec B105: env var name, not a secret


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

    def add_relation(self, relation: Relation) -> str | None:
        relationship = self._relationship_from_dataclass(relation)
        request = WriteRelationshipsRequest(
            updates=[
                RelationshipUpdate(
                    operation=self._write_operation,
                    relationship=relationship,
                )
            ]
        )
        response = self._client.WriteRelationships(request)
        return response.written_at.token

    def get_relations_as_subject(
        self,
        subject: RebacReference,
        *,
        consistency_token: str | None = None,
    ) -> list[Relation]:
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
        return list(
            self._read_relationships(
                filters,
                consistency_token=consistency_token,
            )
        )

    def get_relations_as_resource(
        self,
        resource: RebacReference,
        *,
        consistency_token: str | None = None,
    ) -> list[Relation]:
        filter_ = RelationshipFilter(
            resource_type=resource.type.value,
            optional_resource_id=resource.id,
        )
        return list(
            self._read_relationships(
                [filter_],
                consistency_token=consistency_token,
            )
        )

    def has_permission(
        self,
        subject: RebacReference,
        permission: Action,
        resource: RebacReference,
        *,
        consistency_token: str | None = None,
    ) -> bool:
        request_kwargs = {
            "resource": self._object_reference(resource),
            "permission": permission.value,
            "subject": SubjectReference(object=self._object_reference(subject)),
        }
        if consistency_token:
            request_kwargs["consistency"] = Consistency(
                at_least_as_fresh=ZedToken(token=consistency_token)
            )
        elif self._read_consistency is not None:
            request_kwargs["consistency"] = self._read_consistency
        request = CheckPermissionRequest(**request_kwargs)
        response = self._client.CheckPermission(request)
        return (
            response.permissionship
            == CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
        )

    def sync_schema(self, schema: str) -> str | None:
        """Create or update the SpiceDB schema definition."""

        request = WriteSchemaRequest(schema=schema)
        response = self._client.WriteSchema(request)
        return response.written_at.token

    def _read_relationships(
        self,
        filters: Iterable[RelationshipFilter],
        *,
        consistency_token: str | None = None,
    ) -> Iterator[Relation]:
        """Iterate over relationships matching the filters while de-duplicating."""
        seen: set[Relation] = set()
        for filter_ in filters:
            if consistency_token:
                request = ReadRelationshipsRequest(
                    relationship_filter=filter_,
                    consistency=Consistency(
                        at_least_as_fresh=ZedToken(token=consistency_token)
                    ),
                )
            elif self._read_consistency is not None:
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
