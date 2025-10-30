from __future__ import annotations

from types import TracebackType
from typing import Mapping

from openfga_sdk.client.configuration import ClientConfiguration
from openfga_sdk.models import ListStoresResponse, Store
from openfga_sdk.models.create_store_request import CreateStoreRequest
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
