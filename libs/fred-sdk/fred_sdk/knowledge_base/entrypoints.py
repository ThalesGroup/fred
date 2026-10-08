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

"""
How a Knowledge Base image is started.

One image, two commands. `publish` posts the declaration and exits, so it runs
as a deployment hook; `run` serves runs and does not return. Publishing is
never a side effect of running: two writers on one declaration, with no
ordering between them, is how a rolling upgrade restores a retired one.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence

from fred_sdk.knowledge_base.client import ControlPlaneClient
from fred_sdk.knowledge_base.configuration import (
    PodConfiguration,
    bind_active_configuration,
)
from fred_sdk.knowledge_base.declaration import KnowledgeBaseDeclaration
from fred_sdk.knowledge_base.knowledge_base import KnowledgeBase
from fred_sdk.knowledge_base.logs import (
    configure_logging,
    hold_until_configured,
    release_unconfigured,
)

logger = logging.getLogger(__name__)


def _load(knowledge_base: KnowledgeBase) -> PodConfiguration:
    """Read the configuration once: log as the pod it names, and hand it to runs."""
    try:
        configuration = PodConfiguration.load()
    except BaseException:
        release_unconfigured()
        raise
    bind_active_configuration(configuration)
    configure_logging(
        service=configuration.runtime_id,
        knowledge_base=knowledge_base.id,
        log_format=configuration.observability.logs.format,
    )
    return configuration


def publish_knowledge_base(knowledge_base: KnowledgeBase) -> None:
    """Publish this Knowledge Base's declaration to Control Plane, then return.

    Idempotent, so every deployment of the image replays it and what Fred
    stores stays what is deployed.
    """
    declaration = KnowledgeBaseDeclaration.of(knowledge_base)
    configuration = _load(knowledge_base)

    async def _publish() -> None:
        client = ControlPlaneClient(configuration)
        try:
            await client.publish(declaration)
        finally:
            await client.aclose()

    asyncio.run(_publish())
    logger.info(
        "Published Knowledge Base %s version %s",
        declaration.id,
        declaration.version,
    )


def run_knowledge_base(knowledge_base: KnowledgeBase) -> None:
    """Serve this Knowledge Base's runs until the process is stopped.

    Takes the declaration and nothing else: where runs arrive, which client it
    authenticates as and what it connects to all come from the pod's
    configuration.
    """
    configuration = _load(knowledge_base)
    # Imported here so `publish` needs no workflow engine at all: serving runs
    # is the only thing that does, and it ships as the `knowledge-base` extra.
    try:
        from fred_sdk.knowledge_base import worker
    except ModuleNotFoundError as exc:  # pragma: no cover - install-time guidance
        raise RuntimeError(
            "Serving Knowledge Base runs requires the workflow engine: "
            "install fred-sdk[knowledge-base]"
        ) from exc

    asyncio.run(worker.serve(knowledge_base, configuration))


def knowledge_base_main(
    knowledge_base: KnowledgeBase, argv: Sequence[str] | None = None
) -> int:
    """The whole command-line surface of a Knowledge Base image.

    An author's `__main__` is one call: `raise SystemExit(knowledge_base_main(kb))`.
    """
    parser = argparse.ArgumentParser(
        prog=knowledge_base.id,
        description=knowledge_base.description,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("publish", help="publish the declaration to Fred, then exit")
    commands.add_parser("run", help="serve runs until stopped")

    arguments = parser.parse_args(argv)
    # Nothing is written until the configuration names the pod: see logs.py.
    hold_until_configured()

    if arguments.command == "publish":
        publish_knowledge_base(knowledge_base)
    else:
        run_knowledge_base(knowledge_base)
    return 0
