"""OpenFGA-backed implementation of the relationship authorization engine."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Awaitable

from openfga_sdk.client.client import OpenFgaClient
from openfga_sdk.client.configuration import ClientConfiguration
from openfga_sdk.credentials import CredentialConfiguration, Credentials
from openfga_sdk.exceptions import FgaValidationException
from openfga_sdk.models.metadata import Metadata
from openfga_sdk.models.object_relation import ObjectRelation
from openfga_sdk.models.relation_metadata import RelationMetadata
from openfga_sdk.models.relation_reference import RelationReference
from openfga_sdk.models.tuple_to_userset import TupleToUserset
from openfga_sdk.models.type_definition import TypeDefinition
from openfga_sdk.models.userset import Userset
from openfga_sdk.models.usersets import Usersets
from openfga_sdk.models.write_authorization_model_request import (
    WriteAuthorizationModelRequest,
)

from fred_core.security.models import Resource
from fred_core.security.rebac.openfga_schema import DEFAULT_SCHEMA
from fred_core.security.rebac.rebac_engine import (
    RebacEngine,
    RebacPermission,
    RebacReference,
    Relation,
    RelationType,
)
from fred_core.security.structure import OpenFgaRebacConfig


class OpenFgaRebacEngine(RebacEngine):
    """Evaluates permissions by delegating to an OpenFGA instance."""

    def __init__(
        self,
        config: OpenFgaRebacConfig,
        *,
        token: str | None = None,
        schema: str = DEFAULT_SCHEMA,
    ) -> None:
        resolved_token = token or os.getenv(config.token_env_var)
        if not resolved_token:
            raise ValueError(
                "OpenFGA token must be provided via parameter or environment "
                f"({config.token_env_var})"
            )

        credentials = Credentials(
            method="api_token",
            configuration=CredentialConfiguration(api_token=resolved_token),
        )

        client_config = ClientConfiguration(
            api_url=str(config.api_url),
            store_id=config.store_id,
            authorization_model_id=config.authorization_model_id,
            credentials=credentials,
            timeout_millisec=config.timeout_millisec,
            headers=config.headers,
        )

        self._client = OpenFgaClient(client_config)
        self._config = config
        self._last_model_id: str | None = None

    async def initialize(self) -> None:
        ...
        # if self._config.create_store_if_needed:
        #     await self._create_store_if_not_exists(self._config.store_id)

        # if self._config.sync_schema_on_init:
        #     await self._sync_schema()

    async def add_relation(self, relation: Relation) -> str | None:
        raise NotImplementedError("OpenFGA relation writes are not implemented yet")

    async def delete_relation(self, relation: Relation) -> str | None:
        raise NotImplementedError("OpenFGA relation writes are not implemented yet")

    async def delete_reference_relations(self, reference: RebacReference) -> str | None:
        raise NotImplementedError(
            "OpenFGA bulk relation deletion is not implemented yet"
        )

    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject_type: Resource | None = None,
        consistency_token: str | None = None,
    ) -> list[Relation]:
        raise NotImplementedError("OpenFGA relation listing is not implemented yet")

    async def lookup_resources(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource_type: Resource,
        *,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        raise NotImplementedError("OpenFGA resource lookup is not implemented yet")

    async def lookup_subjects(
        self,
        resource: RebacReference,
        relation: RelationType,
        subject_type: Resource,
        *,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        raise NotImplementedError("OpenFGA subject lookup is not implemented yet")

    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        consistency_token: str | None = None,
    ) -> bool:
        raise NotImplementedError("OpenFGA permission checks are not implemented yet")
