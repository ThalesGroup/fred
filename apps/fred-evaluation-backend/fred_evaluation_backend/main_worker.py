from __future__ import annotations

import asyncio
import logging

from fred_core import log_setup
from fred_core.logs.null_log_store import NullLogStore

from fred_evaluation_backend.config.loader import load_configuration

logger = logging.getLogger(__name__)


async def main() -> None:
    configuration = load_configuration()
    log_setup(
    service_name="fred-evaluation-worker",
    log_level=configuration.app.log_level,
    store=NullLogStore(),
)
    logger.info("Fred evaluation worker starting...")
    # Worker logic will be wired here in Phase 5
    logger.info("Fred evaluation worker ready.")


if __name__ == "__main__":
    asyncio.run(main())