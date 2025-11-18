"""OpenFGA-backed implementation of the relationship authorization engine."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Iterable

from openfga_sdk.client.client import OpenFgaClient
from openfga_sdk.client.configuration import ClientConfiguration
from openfga_sdk.client.models.check_request import ClientCheckRequest
from openfga_sdk.client.models.list_objects_request import ClientListObjectsRequest
from openfga_sdk.client.models.list_users_request import ClientListUsersRequest
from openfga_sdk.client.models.tuple import ClientTuple
from openfga_sdk.client.models.write_request import ClientWriteRequest
from openfga_sdk.credentials import CredentialConfiguration, Credentials
from openfga_sdk.models.consistency_preference import ConsistencyPreference
from openfga_sdk.models.create_store_request import CreateStoreRequest
from openfga_sdk.models.fga_object import FgaObject
from openfga_sdk.models.read_request_tuple_key import ReadRequestTupleKey
from openfga_sdk.models.user import User
from openfga_sdk.models.user_type_filter import UserTypeFilter

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
from fred_core.security.structure import M2MSecurity, OpenFgaRebacConfig

logger = logging.getLogger(__name__)


class OpenFgaRebacEngine(RebacEngine):
    """Evaluates permissions by delegating to an OpenFGA instance."""

    _config: OpenFgaRebacConfig
    _client_credentials: Credentials
    _schema: str
    _authorization_model_id: str | None
    _cached_client: OpenFgaClient | None = None

    def __init__(
        self,
        config: OpenFgaRebacConfig,
        m2m_security: M2MSecurity,
        *,
        token: str | None = None,
        schema: str = DEFAULT_SCHEMA,
    ) -> None:
        super().__init__(m2m_security)

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
        self._authorization_model_id = config.authorization_model_id
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

        options = self._build_options()
        _ = await client.write(body, options)

        # Returning this for now as OpenFGA does not support real consistency tokens (Zanzibar Zookies)
        # for now (https://openfga.dev/docs/interacting/consistency#future-work)
        return ConsistencyPreference.HIGHER_CONSISTENCY

    async def delete_relation(self, relation: Relation) -> str | None:
        client = await self.get_client()

        body = ClientWriteRequest(
            deletes=[OpenFgaRebacEngine._relation_to_tuple(relation)]
        )

        logger.debug("Deleting relation %s", relation)

        options = self._build_options()
        _ = await client.write(body, options)

        # Returning this for now as OpenFGA does not support real consistency tokens (Zanzibar Zookies)
        # for now (https://openfga.dev/docs/interacting/consistency#future-work)
        return ConsistencyPreference.HIGHER_CONSISTENCY

    async def delete_all_relations_of_reference(
        self, reference: RebacReference
    ) -> str | None:
        # Not that easy to do with OpenFGA API yet
        # This has been discussed in their community:
        # - https://github.com/orgs/openfga/discussions/225
        # - https://github.com/orgs/openfga/discussions/341
        #
        # Improvement on the delete api were added in their roadmap:
        # https://github.com/openfga/roadmap/issues/34

        fga_id_to_delete = OpenFgaRebacEngine._reference_to_openfga_id(reference)
        to_delete: list[ClientTuple] = []

        client = await self.get_client()
        body = ReadRequestTupleKey()
        continuation_token: str | None = None

        while continuation_token != "":  # nosec: not a secret token (bandit flags it...)
            options = self._build_options()
            if continuation_token:
                options["continuation_token"] = continuation_token

            res = await client.read(body, options)
            continuation_token = res.continuation_token

            # Filter only tuples related to the given reference
            for tup in res.tuples:
                if (
                    tup.key.user == fga_id_to_delete
                    or tup.key.object == fga_id_to_delete
                ):
                    to_delete.append(
                        ClientTuple(
                            user=tup.key.user,
                            relation=tup.key.relation,
                            object=tup.key.object,
                        )
                    )

        if not to_delete:
            return None

        # Delete all found tuples
        body_delete = ClientWriteRequest(deletes=to_delete)
        logger.debug("Deleting %d relations of reference %s", len(to_delete), reference)
        options = self._build_options()
        _ = await client.write(body_delete, options)

        # Returning this for now as OpenFGA does not support real consistency tokens (Zanzibar Zookies)
        # for now (https://openfga.dev/docs/interacting/consistency#future-work)
        return ConsistencyPreference.HIGHER_CONSISTENCY

    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject_type: Resource | None = None,
        consistency_token: str | None = None,
    ) -> list[Relation]:
        # Only used to sync Keycloakc groups with the rebac engine. Not needed
        # with OpenFGA as we handle this with contextual tuples.
        raise NotImplementedError(
            "OpenFGA relation listing is not implemented as it is not needed"
        )

    async def lookup_resources(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        client = await self.get_client()

        body = ClientListObjectsRequest(
            user=OpenFgaRebacEngine._reference_to_openfga_id(subject),
            relation=permission.value,
            type=resource_type.value,
            contextual_tuples=[
                OpenFgaRebacEngine._relation_to_tuple(rel)
                for rel in (contextual_relations or [])
            ],
        )
        options = self._build_options(consistency=consistency_token)
        response = await client.list_objects(body, options)
        return [
            OpenFgaRebacEngine._openfga_id_to_reference(obj) for obj in response.objects
        ]

    async def lookup_subjects(
        self,
        resource: RebacReference,
        relation: RelationType,
        subject_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        client = await self.get_client()

        userFilters = [UserTypeFilter(type=subject_type.value)]
        # When a group acts as a subject we must point to its "member" relation set.
        if subject_type == Resource.GROUP:
            userFilters[0].relation = "member"

        body = ClientListUsersRequest(
            object=FgaObject(type=resource.type.value, id=resource.id),
            relation=relation.value,
            user_filters=userFilters,
            contextual_tuples=[
                OpenFgaRebacEngine._relation_to_tuple(rel)
                for rel in (contextual_relations or [])
            ],
        )

        options = self._build_options(consistency=consistency_token)

        response = await client.list_users(body, options)
        return [
            OpenFgaRebacEngine._openfga_user_to_reference(user)
            for user in response.users
        ]

    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
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
            contextual_tuples=[
                OpenFgaRebacEngine._relation_to_tuple(rel)
                for rel in (contextual_relations or [])
            ],
        )

        options = self._build_options(consistency=consistency_token)

        response = await client.check(body, options)

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
            response = await client.list_stores({"name": store_name})

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
        self._authorization_model_id = response.authorization_model_id
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

    def _build_options(self, **options: object) -> dict[str, object]:
        filtered_options = {k: v for k, v in options.items() if v is not None}
        if self._authorization_model_id:
            filtered_options.setdefault(
                "authorization_model_id", self._authorization_model_id
            )
        return filtered_options

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

    @staticmethod
    def _openfga_id_to_reference(openfga_id: str) -> RebacReference:
        type_str, id_str = openfga_id.split(":", 1)

        # Split on # to remove possible relation suffixes like "#member"
        id_str = id_str.split("#", 1)[0]

        return RebacReference(
            type=Resource(type_str),
            id=id_str,
        )

    @staticmethod
    def _openfga_user_to_reference(user: User) -> RebacReference:
        if user.object:
            encoded_id = f"{user.object.type}:{user.object.id}"
        elif user.userset:
            relation_suffix = (
                f"#{user.userset.relation}" if user.userset.relation else ""
            )
            encoded_id = f"{user.userset.type}:{user.userset.id}{relation_suffix}"
        else:
            raise ValueError("OpenFGA user response missing object and userset")

        return OpenFgaRebacEngine._openfga_id_to_reference(encoded_id)
