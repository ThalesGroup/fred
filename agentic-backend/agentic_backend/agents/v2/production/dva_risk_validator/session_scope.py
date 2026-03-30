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

"""Reusable session-scope merge seam for graph-generated artifacts."""

from __future__ import annotations

from agentic_backend.core.agents.runtime_context import RuntimeContext


def merge_session_scope(
    runtime_context: RuntimeContext | None,
    *,
    generated_document_uids: list[str],
    fallback_search_policy: str = "hybrid",
) -> RuntimeContext:
    """
    Merge generated artifact document UIDs into runtime retrieval scope.

    Why this exists:
    - graph agents need a reusable way to keep original DVA scope and add newly
      generated report/index artifacts so follow-up QA can search both

    How to use:
    - call this at graph finalization after artifact publication
    - persist or return the resulting context through your normal session flow

    Example:
    ```python
    merged = merge_session_scope(
        runtime_context,
        generated_document_uids=["doc-report", "doc-index"],
        fallback_search_policy="hybrid",
    )
    ```
    """

    base = (
        runtime_context.model_copy(deep=True) if runtime_context else RuntimeContext()
    )

    existing_uids = list(base.selected_document_uids or [])
    for uid in generated_document_uids:
        normalized = uid.strip()
        if normalized and normalized not in existing_uids:
            existing_uids.append(normalized)

    base.selected_document_uids = existing_uids
    base.include_session_scope = True
    if not base.search_policy:
        base.search_policy = fallback_search_policy
    return base
