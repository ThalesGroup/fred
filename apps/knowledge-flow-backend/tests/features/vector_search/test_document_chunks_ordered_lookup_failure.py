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
`get_document_chunks_ordered` only ever caught `NotImplementedError` around
`get_chunks_for_document` -- every concrete vector store used to swallow a
genuine backend failure into `[]` on its own, so that narrow catch was
enough to make the whole call graceful either way. Now that every backend
raises on a real fetch failure (see `base_vector_store.py`, the fast-ingest
delete-authorization fix), a backend outage here must surface as a failure
too, not silently degrade to "this document has no chunks" -- pinned here so
the behavior stays intentional rather than an untested side effect.
"""

from __future__ import annotations

import pytest
from fred_core import KeycloakUser

from knowledge_flow_backend.features.vector_search.vector_search_service import VectorSearchService


class _FailingChunkStore:
    def get_chunks_for_document(self, document_uid: str):
        raise RuntimeError("simulated backend outage")


def _user() -> KeycloakUser:
    return KeycloakUser(uid="alice", username="alice", roles=[], email=None)


@pytest.mark.asyncio
async def test_get_document_chunks_ordered_propagates_a_lookup_failure() -> None:
    service = VectorSearchService.__new__(VectorSearchService)
    service.vector_store = _FailingChunkStore()

    with pytest.raises(RuntimeError):
        await service.get_document_chunks_ordered(user=_user(), document_uid="doc-1", limit=200)
