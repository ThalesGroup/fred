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
    # Linux-only: read current RSS/VMS from /proc.
    try:
        with open("/proc/self/statm", "r", encoding="utf-8") as handle:
            parts = handle.read().strip().split()
        if len(parts) >= 2:
            page_size = os.sysconf("SC_PAGE_SIZE")
            vms_mb = (int(parts[0]) * page_size) / (1024 * 1024)
            rss_mb = (int(parts[1]) * page_size) / (1024 * 1024)
            return rss_mb, vms_mb
    except Exception:
        return None, None
    return None, None


def _get_open_fd_count() -> Optional[int]:
    # Linux-only: count file descriptors in /proc.
    try:
        return len(os.listdir("/proc/self/fd"))
    except Exception:
        return None


def _get_memory_limit_mb() -> Optional[float]:
    # Prefer cgroup limits so memory % is meaningful inside containers.
    candidates = (
        "/sys/fs/cgroup/memory.max",  # cgroup v2
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",  # cgroup v1
    )
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = handle.read().strip()
            if raw == "max":
                continue
            value = int(raw)
            if value <= 0 or value >= (1 << 60):
                continue
            return value / (1024 * 1024)
        except Exception:
            logger.debug("Could not read memory limit from %s", path)
            continue

    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        kb = int(parts[1])
                        return kb / 1024.0
    except Exception:
        return None
    return None


async def emit_process_kpis(interval_s: float, kpi_writer) -> None:
    """
    Emit process KPIs on a fixed cadence.

    This facility is a complement to k8 prometheus metrics exporters. It makes
    process-level KPIs available in the same KPI system as other application KPIs,
    enabling unified logging, alerting, and dashboards.

    Linux-only contract:
    - RSS/VMS and open_fds come from /proc.
    - Memory % uses cgroup limits when present (K8s), otherwise host MemTotal.
    - CPU % is process CPU-time delta / wall-time delta (can exceed 100%).
    """
    actor = KPIActor(type="system")
    mem_limit_mb = _get_memory_limit_mb()
    last_cpu_time: Optional[float] = None
    last_ts = time.monotonic()
    while True:
        try:
            now = time.monotonic()
            cpu_pct_value: Optional[float] = None
            rss_pct_value: Optional[float] = None
            elapsed_since_last = now - last_ts

            try:
                proc_times = os.times()
                cpu_time: Optional[float] = proc_times.user + proc_times.system
            except Exception:
                cpu_time = None

            rss_mb, vms_mb = _get_process_memory_mb()

            if rss_mb is not None:
                kpi_writer.gauge("process.memory.rss_mb", rss_mb, actor=actor)
                if mem_limit_mb:
                    rss_pct_value = rss_mb / mem_limit_mb * 100.0
                    kpi_writer.gauge(
                        "process.memory.rss_percent",
                        rss_pct_value,
                        unit="percent",
                        actor=actor,
                    )
            if vms_mb is not None:
                kpi_writer.gauge("process.memory.vms_mb", vms_mb, actor=actor)
            if mem_limit_mb:
                kpi_writer.gauge(
                    "process.memory.limit_mb",
                    mem_limit_mb,
                    unit="mb",
                    actor=actor,
                )
            fd_count = _get_open_fd_count()
            if fd_count is not None:
                kpi_writer.gauge("process.open_fds", fd_count, actor=actor)

            if cpu_time is not None:
                if last_cpu_time is None:
                    cpu_pct_value = 0.0
                    kpi_writer.gauge(
                        "process.cpu.percent",
                        cpu_pct_value,
                        unit="percent",
                        actor=actor,
                    )
                else:
                    if elapsed_since_last > 0:
                        delta_cpu = cpu_time - last_cpu_time
                        if delta_cpu < 0:
                            delta_cpu = 0.0
                        cpu_pct_value = (delta_cpu / elapsed_since_last) * 100.0
                        kpi_writer.gauge(
                            "process.cpu.percent",
                            cpu_pct_value,
                            unit="percent",
                            actor=actor,
                        )
                last_cpu_time = cpu_time
                last_ts = now
            else:
                last_cpu_time = None
                last_ts = now

            logger.debug(
                "[KPI][process] cpu_pct=%s rss_mb=%s rss_pct=%s vms_mb=%s open_fds=%s",
                f"{cpu_pct_value:.2f}" if cpu_pct_value is not None else "n/a",
                f"{rss_mb:.2f}" if rss_mb is not None else "n/a",
                f"{rss_pct_value:.2f}" if rss_pct_value is not None else "n/a",
                f"{vms_mb:.2f}" if vms_mb is not None else "n/a",
                f"{fd_count}" if fd_count is not None else "n/a",
            )
        except Exception:
            logger.exception("Process KPI tick failed; continuing")
        await asyncio.sleep(interval_s)
