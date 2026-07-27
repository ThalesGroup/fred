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

import logging

from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.security.rebac.openfga_engine import OpenFgaRebacEngine
from fred_core.security.rebac.rebac_engine import RebacEngine
from fred_core.security.structure import (
    OpenFgaRebacConfig,
    SecurityConfiguration,
)

logger = logging.getLogger(__name__)


def rebac_factory(
    security_config: SecurityConfiguration,
    *,
    kpi_writer: BaseKPIWriter | None = None,
) -> RebacEngine:
    """Factory function to create a ReBAC engine based on the provided configuration.

    `kpi_writer`, when provided, lets the engine emit `rebac.call_latency_ms` /
    `rebac.call_total` per OpenFGA operation (see `openfga_engine._rebac_timer`).
    """
    rebac_config = security_config.rebac

    oidc_enabled = security_config.user.enabled and security_config.m2m.enabled
    if not oidc_enabled or rebac_config is None or not rebac_config.enabled:
        return NoopRebacEngine()

    if isinstance(rebac_config, OpenFgaRebacConfig):
        logger.info(
            "[AUTH] Initializing OpenFGA ReBAC engine (api_url=%s, store_name=%s)",
            rebac_config.api_url,
            rebac_config.store_name,
        )
        return OpenFgaRebacEngine(rebac_config, kpi_writer=kpi_writer)
    else:
        # Should not happen
        raise ValueError(
            f"Unsupported ReBAC engine type: {getattr(rebac_config, 'type', rebac_config)}"
        )
