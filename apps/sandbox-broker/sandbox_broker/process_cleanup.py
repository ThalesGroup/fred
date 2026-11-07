# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Remove code processes before a conversation workload can be reused."""

from __future__ import annotations

from fred_sdk.contracts.sandbox import SandboxError

from .command import CommandRunner

_SWEEP = """\
import os, signal, time
me = os.getpid()
for attempt in range(20):
    survivors = []
    for name in os.listdir('/proc'):
        if not name.isdigit():
            continue
        pid = int(name)
        if pid in (1, me):
            continue
        try:
            with open('/proc/%d/status' % pid) as status:
                state = next(line for line in status if line.startswith('State:')).split()[1]
            if state == 'Z':
                raise SystemExit(1)
            os.kill(pid, signal.SIGKILL)
            survivors.append(pid)
        except ProcessLookupError:
            pass
    if not survivors:
        break
    time.sleep(0.025)
else:
    raise SystemExit(1)
"""


async def remove_code_processes(runner: CommandRunner, prefix: list[str]) -> None:
    try:
        result = await runner.run(
            [*prefix, "python", "-c", _SWEEP], timeout=5, output_limit=1024
        )
    except Exception as exc:
        raise SandboxError("backend_failed") from exc
    if result.returncode != 0:
        raise SandboxError("backend_failed")
