# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Run installed capability preparation hooks without an HTTP serving pod."""

import asyncio

from fred_runtime.app import load_agent_pod_config
from fred_runtime.capabilities.preparation_worker import run_preparation_worker


def main() -> None:
    asyncio.run(run_preparation_worker(load_agent_pod_config()))


if __name__ == "__main__":
    main()
