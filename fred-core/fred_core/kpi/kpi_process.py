# Copyright Thales 2025
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

import asyncio
import logging
import os
import time
from typing import Optional, Tuple

from fred_core.kpi.kpi_writer_structures import KPIActor

logger = logging.getLogger(__name__)


def _get_process_memory_mb() -> Tuple[Optional[float], Optional[float]]:
    # Prefer /proc for current RSS/VMS; fall back to max RSS if unavailable.
    try:
        with open("/proc/self/statm", "r", encoding="utf-8") as handle:
            parts = handle.read().strip().split()
        if len(parts) >= 2:
            page_size = os.sysconf("SC_PAGE_SIZE")
            vms_mb = (int(parts[0]) * page_size) / (1024 * 1024)
            rss_mb = (int(parts[1]) * page_size) / (1024 * 1024)
            return rss_mb, vms_mb
    except Exception:
        logger.warning("Failed to read /proc/self/statm for memory usage")
        pass

    try:
        import resource

        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return rss_kb / 1024.0, None
    except Exception:
        return None, None


def _get_open_fd_count() -> Optional[int]:
    try:
        return len(os.listdir("/proc/self/fd"))
    except Exception:
        return None


async def emit_process_kpis(interval_s: float, kpi_writer) -> None:
    actor = KPIActor(type="system")
    last_cpu_time: Optional[float] = None
    last_ts = time.monotonic()
    while True:
        now = time.monotonic()
        try:
            proc_times = os.times()
            cpu_time = proc_times.user + proc_times.system
        except Exception:
            cpu_time = None

        rss_mb, vms_mb = _get_process_memory_mb()
        if rss_mb is not None:
            kpi_writer.gauge("process.memory.rss_mb", rss_mb, actor=actor)
        if vms_mb is not None:
            kpi_writer.gauge("process.memory.vms_mb", vms_mb, actor=actor)
        fd_count = _get_open_fd_count()
        if fd_count is not None:
            kpi_writer.gauge("process.open_fds", fd_count, actor=actor)
        if cpu_time is not None and last_cpu_time is not None:
            elapsed = now - last_ts
            if elapsed > 0:
                cpu_pct = (cpu_time - last_cpu_time) / elapsed * 100.0
                kpi_writer.gauge("process.cpu.percent", cpu_pct, actor=actor)
        if cpu_time is not None:
            last_cpu_time = cpu_time
            last_ts = now
        await asyncio.sleep(interval_s)
