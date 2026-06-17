from __future__ import annotations

import asyncio
import logging
import os

from fred_core import log_setup
from fred_core.logs.null_log_store import NullLogStore
from fred_core.sql import create_async_engine_from_config

from fred_evaluation_backend.config.loader import load_configuration
from fred_evaluation_backend.execution.control_plane_client import ControlPlaneClient
from fred_evaluation_backend.workers.runner import CampaignRunner

logger = logging.getLogger(__name__)


async def main() -> None:
    configuration = load_configuration()
    log_setup(
        service_name="fred-evaluation-worker",
        log_level=configuration.app.log_level,
        store=NullLogStore(),
    )
    logger.info("Fred evaluation worker starting...")

    engine = create_async_engine_from_config(configuration.database)
    cp_token = os.environ.get(configuration.control_plane.credential_ref)
    cp_client = ControlPlaneClient(
        base_url=configuration.control_plane.base_url,
        service_token=cp_token,
        runtime_base_url=configuration.control_plane.runtime_base_url,
    )
    runner = CampaignRunner(config=configuration, engine=engine, cp_client=cp_client)

    logger.info("Fred evaluation worker ready.")
    await runner.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
