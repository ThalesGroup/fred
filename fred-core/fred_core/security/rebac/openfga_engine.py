"""OpenFGA-backed implementation of the relationship authorization engine."""

from __future__ import annotations

import asyncio
import json
import logging
import os

from openfga_sdk.client.client import OpenFgaClient
from openfga_sdk.client.configuration import ClientConfiguration
from openfga_sdk.client.models.check_request import ClientCheckRequest
from openfga_sdk.client.models.tuple import ClientTuple
from openfga_sdk.client.models.write_request import ClientWriteRequest
from openfga_sdk.credentials import CredentialConfiguration, Credentials
from openfga_sdk.models.create_store_request import CreateStoreRequest

from fred_core.security.models import Resource
from fred_core.security.rebac.openfga_schema import (
    DEFAULT_SCHEMA,
)
from fred_core.security.rebac.rebac_engine import (
    RebacEngine,
    RebacPermission,
    RebacReference,
    Relation,
    RelationType,
)
from fred_core.security.structure import OpenFgaRebacConfig

logger = logging.getLogger(__name__)


class OpenFgaRebacEngine(RebacEngine):
    """Evaluates permissions by delegating to an OpenFGA instance."""

    _config: OpenFgaRebacConfig
    _client_credentials: Credentials
    _schema: str
    _cached_client: OpenFgaClient | None = None

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

        self._client_credentials = Credentials(
            method="api_token",
            configuration=CredentialConfiguration(api_token=resolved_token),
        )

        self._config = config
        self._schema = schema
        self._client_lock = asyncio.Lock()

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Public RebacEngine methods
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    async def add_relation(self, relation: Relation) -> str | None:
        client = await self.get_client()

        body = ClientWriteRequest(
            writes=[OpenFgaRebacEngine._relation_to_tuple(relation)]
        )

        logger.debug("Adding relation %s", relation)

        _ = await client.write(body)

        return None

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
        client = await self.get_client()

        logger.debug(
            "Checking permission %s for subject %s on resource %s",
            permission,
            subject,
            resource,
        )
        body = ClientCheckRequest(
            user=OpenFgaRebacEngine._reference_to_openfga_id(subject),
            relation=permission.value,
            object=OpenFgaRebacEngine._reference_to_openfga_id(resource),
        )

        response = await client.check(body)

        return response.allowed

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Client and initialization helpers
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def _create_client_with_no_store(self) -> OpenFgaClient:
        """Create an OpenFGA client without a store ID (needed to list stores or create one)."""
        client_config = ClientConfiguration(
            api_url=str(self._config.api_url).rstrip("/"),
            credentials=self._client_credentials,
            timeout_millisec=self._config.timeout_millisec,
            headers=self._config.headers,
        )
        return OpenFgaClient(client_config)

    def _create_client_with_store_id(self, store_id: str) -> OpenFgaClient:
        """Create an OpenFGA client configured with the given store ID."""
        client = self._create_client_with_no_store()
        client.set_store_id(store_id)
        return client

    async def _get_store_id(self, store_name: str) -> str | None:
        async with self._create_client_with_no_store() as client:
            response = await client.list_stores()

        for store in response.stores:
            if store.name == store_name:
                return store.id

        return None

    async def _create_store(self, store_name: str) -> str:
        async with self._create_client_with_no_store() as client:
            response = await client.create_store(CreateStoreRequest(name=store_name))
        return response.id

    async def sync_schema(self, fga_client_with_store: OpenFgaClient) -> str:
        response = await fga_client_with_store.write_authorization_model(
            json.loads(self._schema)
        )
        return response.authorization_model_id

    async def _initialize_client_and_store(self) -> OpenFgaClient:
        """If needed, create store, sync schema, and return client."""
        # Try to retrieve store id
        store_id = await self._get_store_id(self._config.store_name)
        if store_id is None:
            if not self._config.create_store_if_needed:
                raise ValueError(
                    f"OpenFGA store '{self._config.store_name}' does not exist"
                )

            # If it does not exist, create it
            store_id = await self._create_store(self._config.store_name)

        client = self._create_client_with_store_id(store_id)

        # Sync the schema
        if self._config.sync_schema_on_init:
            await self.sync_schema(client)

        return client

    async def get_client(self) -> OpenFgaClient:
        """Lazily initialize and cache an OpenFGA client with store ID."""
        if self._cached_client is None:
            async with self._client_lock:
                if self._cached_client is None:
                    self._cached_client = await self._initialize_client_and_store()

        return self._cached_client

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Helpers
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    @staticmethod
    def _relation_to_tuple(relation: Relation) -> ClientTuple:
        subject_id = OpenFgaRebacEngine._reference_to_openfga_id(relation.subject)
        object_id = OpenFgaRebacEngine._reference_to_openfga_id(relation.resource)

        # When a group acts as a subject we must point to its "member" relation set.
        if relation.subject.type == Resource.GROUP:
            subject_id += "#member"

        return ClientTuple(
            user=subject_id,
            relation=relation.relation.value,
            object=object_id,
        )

    @staticmethod
    def _reference_to_openfga_id(reference: RebacReference) -> str:
        return f"{reference.type.value}:{reference.id}"
