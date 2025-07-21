# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Temporal worker responsible for running ingestion pipelines.

This worker connects to the Temporal service, registers all ingestion-related
activities and workflows, and listens on the configured task queue.

It is launched in a background thread from main.py during application startup.
"""

import logging
import concurrent.futures
from temporalio.client import Client
from temporalio.worker import Worker

from app.common.structures import TemporalSchedulerConfig
from app.features.scheduler.activities import (
    extract_metadata_activity,
    process_document_activity,
    vectorize_activity,
)
from app.features.scheduler.workflow import Process, ExtractMetadata, PreProcess, Vectorize

# Use basic logging instead of rich within the Temporal worker
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_worker(config: TemporalSchedulerConfig):
    """
    Connect to Temporal and start the ingestion worker.

    Args:
        config (TemporalSchedulerConfig): Temporal connection + task queue config
    """
    logger.info(f"🔗 Connecting to Temporal at {config.host} (namespace={config.namespace})")
    client = await Client.connect(
        target_host=config.host,
        namespace=config.namespace,
    )
    logger.info(f"✅ Connected to Temporal. Registering worker on queue: '{config.task_queue}'")

    # Use thread pool executor for sync activities
    executor = concurrent.futures.ThreadPoolExecutor()
    worker = Worker(
        client=client,
        task_queue=config.task_queue,
        workflows=[
            Process,
            ExtractMetadata,
            PreProcess,
            Vectorize,
        ],
        activities=[
            extract_metadata_activity,
            process_document_activity,
            vectorize_activity,
        ],
        activity_executor=executor,
    )

    logger.info("🚀 Temporal worker is now running and ready to receive ingestion jobs.")
    await worker.run()
