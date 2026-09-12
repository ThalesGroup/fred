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
Where a definition's runs are dispatched.

Part of the contract, not a private detail: Control Plane and the pod's worker
must derive the identical string, and a worker that is one day not this SDK has
to be able to derive it too. Deliberately absent from the author-facing exports
— an author never names a queue.
"""

from __future__ import annotations

from fred_core import knowledge_base_catalog_id


def task_queue_for(name: str) -> str:
    """Return the task queue a definition's runs are dispatched on.

    The queue *is* the catalog id built by the same fred-core function Control
    Plane uses, so the dispatching side and the worker side cannot disagree by
    construction. The contributed name already carries its prefix, so two
    contributors never share a queue.
    """
    if not name:
        raise ValueError("name must not be empty")
    return knowledge_base_catalog_id(name)
