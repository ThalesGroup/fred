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

"""Pod-local admission control for heavy PPT Filler CPU work (#2183).

``fill_ppt_template``, ``/analyze`` and ``validate_config`` all run
python-pptx/Pillow work off the event loop via ``asyncio.to_thread``. Without
a bound, a burst of concurrent calls can still exhaust the pod's thread pool
and starve every other agent sharing it. This is a plain module-level
counter, not an ``asyncio.Semaphore``: the check-then-increment has no
``await`` between the two steps, so it is race-free on the single-threaded
event loop without needing a non-blocking-acquire workaround.

In-process / per-pod only by design (CONVENTIONS.md perf section — no
cross-replica coordination needed). Callers MUST fail fast when the slot is
unavailable, never queue: see the acceptance criteria on #2183.
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
