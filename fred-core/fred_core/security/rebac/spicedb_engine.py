"""SpiceDB-backed implementation of the relationship authorization engine."""

from __future__ import annotations

import os

from authzed.api.v1 import (
    CheckPermissionRequest,
    CheckPermissionResponse,
    Consistency,
    LookupResourcesRequest,
    ObjectReference,
    Relationship,
    RelationshipUpdate,
    SubjectReference,
    SyncClient,
    WriteRelationshipsRequest,
    WriteSchemaRequest,
    ZedToken,
)
from grpcutil import bearer_token_credentials, insecure_bearer_token_credentials

from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import (
    RebacEngine,
    RebacPermission,
    RebacReference,
    Relation,
)
from fred_core.security.rebac.schema import DEFAULT_SCHEMA
from fred_core.security.structure import SpiceDbRebacConfig


class SpiceDbRebacEngine(RebacEngine):
    """Evaluates permissions by delegating to a SpiceDB instance."""

    def __init__(
        self,
        config: SpiceDbRebacConfig,
        *,
        token: str | None = None,
        read_consistency: Consistency | None = None,
        write_operation: RelationshipUpdate._Operation.ValueType = RelationshipUpdate.Operation.OPERATION_TOUCH,
        schema: str | None = DEFAULT_SCHEMA,
    ) -> None:
        if not config.endpoint:
            raise ValueError("SpiceDB endpoint must be provided in configuration")

        resolved_token = token or os.getenv(config.token_env_var)
        if not resolved_token:
            raise ValueError(
                f"SpiceDB token must be provided via parameter or environment ({config.token_env_var})",
            )

        if config.insecure:
            credentials = insecure_bearer_token_credentials(resolved_token)
        else:
            credentials = bearer_token_credentials(resolved_token)

        self._client = SyncClient(config.endpoint, credentials)

        self._read_consistency = read_consistency
        self._write_operation = write_operation

        if schema and config.sync_schema_on_init:
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

    def delete_relation(self, relation: Relation) -> str | None:
        relationship = self._relationship_from_dataclass(relation)
        request = WriteRelationshipsRequest(
            updates=[
                RelationshipUpdate(
                    operation=RelationshipUpdate.Operation.OPERATION_DELETE,
                    relationship=relationship,
                )
            ]
        )
        response = self._client.WriteRelationships(request)
        return response.written_at.token

    def lookup_resources(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource_type: Resource,
        *,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        request_kwargs = {
            "resource_object_type": resource_type.value,
            "permission": permission.value,
            "subject": SubjectReference(object=self._object_reference(subject)),
        }
        if consistency_token:
            request_kwargs["consistency"] = Consistency(
                at_least_as_fresh=ZedToken(token=consistency_token)
            )
        elif self._read_consistency is not None:
            request_kwargs["consistency"] = self._read_consistency

        request = LookupResourcesRequest(**request_kwargs)
        return [
            RebacReference(type=resource_type, id=response.resource_object_id)
            for response in self._client.LookupResources(request)
        ]

    def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
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
