import logging

from fred_core.security.rebac.openfga_engine import OpenFgaRebacEngine
from fred_core.security.rebac.rebac_engine import RebacEngine
from fred_core.security.rebac.spicedb_engine import SpiceDbRebacEngine
from fred_core.security.structure import (
    OpenFgaRebacConfig,
    RebacConfiguration,
    SpiceDbRebacConfig,
)

logger = logging.getLogger(__name__)


def rebac_factory(rebac_config: RebacConfiguration) -> RebacEngine:
    """Factory function to create a ReBAC engine based on the provided configuration."""
    if isinstance(rebac_config, SpiceDbRebacConfig):
        logger.info(
            "Initializing SpiceDB ReBAC engine (endpoint=%s, insecure=%s)",
            rebac_config.endpoint,
            rebac_config.insecure,
        )
        return SpiceDbRebacEngine(rebac_config)
    elif isinstance(rebac_config, OpenFgaRebacConfig):
        logger.info(
            "Initializing OpenFGA ReBAC engine (api_url=%s, store_name=%s)",
            rebac_config.api_url,
            rebac_config.store_name,
        )
        return OpenFgaRebacEngine(rebac_config)
    else:
        # Should not happen
        raise ValueError(
            f"Unsupported ReBAC engine type: {getattr(rebac_config, 'type', rebac_config)}"
        )
