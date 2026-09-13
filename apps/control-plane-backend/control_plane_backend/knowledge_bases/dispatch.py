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
What Fred starts when an instance runs, and where it starts it.

Both sides derive the queue from the definition's own name through the same
function, so a pod polling one queue and Fred dispatching to another is not a
mistake that can be made. Everything else about the engine stays here: an
author never names a queue, a workflow or an attempt budget.
"""

from __future__ import annotations

from fred_sdk.knowledge_base._workflow import (
    SYNCHRONIZE_WORKFLOW,
    SynchronizeInput,
)
from fred_sdk.knowledge_base.routing import task_queue_for

__all__ = [
    "SYNCHRONIZE_WORKFLOW",
    "run_input",
    "task_queue_for_definition",
]


def task_queue_for_definition(definition_id: str) -> str:
    """The queue this definition's pod polls, derived from its name alone."""
    return task_queue_for(definition_id)


def run_input(
    *,
    definition_id: str,
    instance_id: str,
    team_id: str,
    max_attempts: int,
) -> SynchronizeInput:
    """The whole of what a run is told about itself.

    Identifiers plus the attempt budget Fred chose. No configuration value and
    no secret: the engine keeps a workflow's input for as long as its retention
    policy says, replicated, so only what is safe to keep for ever goes in. The
    pod fetches the rest per run, against the identity it authenticates with.
    """
    return SynchronizeInput(
        definition_id=definition_id,
        instance_id=instance_id,
        team_id=team_id,
        max_attempts=max_attempts,
    )
