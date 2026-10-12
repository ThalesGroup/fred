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

"""Pod-local admission control for heavy pptx_generator CPU work.

Bounds `asyncio.to_thread` work so a burst cannot starve the pod's thread pool.
A plain counter is race-free here: no `await` between check and increment.
Callers MUST fail fast when no slot is available, never queue.
"""

from __future__ import annotations

MAX_CONCURRENT_HEAVY_JOBS = 4

_active_jobs = 0


def acquire_heavy_job_slot() -> bool:
    """Reserve one slot. Returns False (no slot reserved) when at the bound."""
    global _active_jobs
    if _active_jobs >= MAX_CONCURRENT_HEAVY_JOBS:
        return False
    _active_jobs += 1
    return True


def release_heavy_job_slot() -> None:
    """Release a slot reserved by a successful :func:`acquire_heavy_job_slot`."""
    global _active_jobs
    _active_jobs = max(0, _active_jobs - 1)
