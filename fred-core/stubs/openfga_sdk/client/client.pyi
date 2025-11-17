from __future__ import annotations

from types import TracebackType
from typing import Mapping

from openfga_sdk.client.configuration import ClientConfiguration
from openfga_sdk.client.models.check_request import ClientCheckRequest
from openfga_sdk.client.models.list_objects_request import ClientListObjectsRequest
from openfga_sdk.client.models.list_users_request import ClientListUsersRequest
from openfga_sdk.client.models.write_request import ClientWriteRequest
from openfga_sdk.client.models.write_response import ClientWriteResponse
from openfga_sdk.models import ListStoresResponse, Store
from openfga_sdk.models.check_response import CheckResponse
from openfga_sdk.models.create_store_request import CreateStoreRequest
from openfga_sdk.models.list_objects_response import ListObjectsResponse
from openfga_sdk.models.list_users_response import ListUsersResponse
from openfga_sdk.models.read_request_tuple_key import ReadRequestTupleKey
from openfga_sdk.models.read_response import ReadResponse
from openfga_sdk.models.write_authorization_model_request import (
    WriteAuthorizationModelRequest,
)
from openfga_sdk.models.write_authorization_model_response import (
    WriteAuthorizationModelResponse,
)

class OpenFgaClient:
    def __init__(self, configuration: ClientConfiguration) -> None: ...
    async def __aenter__(self) -> OpenFgaClient: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...
    async def close(self) -> None: ...
    def set_store_id(self, value: str) -> None: ...
    async def list_stores(
        self,
        options: Mapping[str, object] | None = ...,
    ) -> ListStoresResponse: ...
    async def create_store(
        self,
        body: CreateStoreRequest,
        options: Mapping[str, object] | None = ...,
    ) -> Store: ...
    async def write_authorization_model(
        self,
        body: WriteAuthorizationModelRequest,
        options: Mapping[str, object] | None = ...,
    ) -> WriteAuthorizationModelResponse: ...
    async def write(
        self,
        body: ClientWriteRequest,
        options: Mapping[str, object] | None = ...,
    ) -> ClientWriteResponse: ...
    async def check(
        self,
        body: ClientCheckRequest,
        options: Mapping[str, object] | None = ...,
    ) -> CheckResponse: ...
    async def list_objects(
        self,
        body: ClientListObjectsRequest,
        options: Mapping[str, object] | None = ...,
    ) -> ListObjectsResponse: ...
    async def list_users(
        self,
        body: ClientListUsersRequest,
        options: Mapping[str, object] | None = ...,
    ) -> ListUsersResponse: ...
    async def read(
        self,
        body: ReadRequestTupleKey,
        options: Mapping[str, object] | None = ...,
    ) -> ReadResponse: ...
