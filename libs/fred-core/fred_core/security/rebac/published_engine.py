# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""OpenFGA transport bound to the publication already validated at startup."""

from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.security.rebac.authorization_binding import AuthorizationBinding
from fred_core.security.rebac.openfga_engine import OpenFgaRebacEngine
from fred_core.security.structure import OpenFgaRebacConfig
from openfga_sdk.client.client import OpenFgaClient
from openfga_sdk.client.configuration import ClientConfiguration


class PublishedOpenFgaRebacEngine(OpenFgaRebacEngine):
    """Reuse checks, credentials and KPIs without store/model discovery or mutation.

    The immutable publication remains authoritative after closing/recreating the
    internal client. Configuration's Swift creation/synchronization options and
    optional model ID do not participate in this consumer's startup.
    """

    def __init__(
        self,
        config: OpenFgaRebacConfig,
        binding: AuthorizationBinding,
        *,
        kpi_writer: BaseKPIWriter,
    ) -> None:
        super().__init__(config, kpi_writer=kpi_writer)
        self._binding = binding
        self._authorization_model_id = binding.model_id

    async def _initialize_client_and_store(self) -> OpenFgaClient:
        return OpenFgaClient(
            ClientConfiguration(
                api_url=str(self._config.api_url).rstrip("/"),
                store_id=self._binding.active_store,
                authorization_model_id=self._binding.model_id,
                credentials=self._client_credentials,
                timeout_millisec=self._config.timeout_millisec,
                headers=self._config.headers,
            )
        )

    def _build_options(self, **options: object) -> dict[str, object]:
        options = super()._build_options(**options)
        options["store_id"] = self._binding.active_store
        options["authorization_model_id"] = self._binding.model_id
        options["consistency"] = self.HIGHER_CONSISTENCY
        return options

    async def sync_schema(self, fga_client_with_store: OpenFgaClient) -> str:
        raise RuntimeError(
            "The published authorization model is owned by Control Plane"
        )
