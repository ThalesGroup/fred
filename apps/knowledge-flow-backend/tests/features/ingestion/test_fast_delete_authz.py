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

"""Fast-ingest delete authorization (#2223: session-scoped attachments have no
ReBAC tuple, so a document-level ReBAC check can never resolve to True for
them -- ownership must be proven via the vector chunk's own scope/user_id
metadata instead, the same mechanism `summarize_document` already uses for
reads on this document class).

These tests pin the authorization decision:
- an admin (holds can_manage_platform) skips the per-document ownership check;
- a non-admin owner (their own session-scoped chunks exist) passes;
- a non-admin non-owner is refused.
Authentication itself is enforced by the endpoint dependency and is not waived.
"""

from __future__ import annotations

import pytest
from fred_core import (
    ORGANIZATION_ID,
    AuthorizationError,
    KeycloakUser,
    OrganizationPermission,
)

from knowledge_flow_backend.features.ingestion.ingestion_controller import (
    _authorize_fast_ingest_delete,
)


def _user(uid: str = "svc-control-plane") -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, email=None, roles=[])


class _FakeRebac:
    """Records the platform-admin bypass check the authorizer makes."""

    def __init__(self, *, is_platform_admin: bool) -> None:
        self._is_platform_admin = is_platform_admin

    async def has_user_permission(self, user, permission, resource_id, **_kw) -> bool:
        assert permission == OrganizationPermission.CAN_MANAGE_PLATFORM
        assert resource_id == ORGANIZATION_ID
        return self._is_platform_admin


class _FakeVectorStore:
    """Records the ownership check the authorizer makes."""

    def __init__(self, *, owns_document: bool) -> None:
        self._owns_document = owns_document
        self.ownership_checked = False

    def owns_session_document(self, document_uid: str, user_id: str) -> bool:
        self.ownership_checked = True
        assert document_uid == "doc-1"
        return self._owns_document


@pytest.mark.asyncio
async def test_platform_admin_bypasses_document_ownership() -> None:
    rebac = _FakeRebac(is_platform_admin=True)
    vector_store = _FakeVectorStore(owns_document=False)
    # Admin: allowed even though it owns nothing, and the ownership check is skipped.
    await _authorize_fast_ingest_delete(rebac, _user(), "doc-1", vector_store)
    assert vector_store.ownership_checked is False


@pytest.mark.asyncio
async def test_non_admin_owner_passes_ownership_check() -> None:
    rebac = _FakeRebac(is_platform_admin=False)
    vector_store = _FakeVectorStore(owns_document=True)
    await _authorize_fast_ingest_delete(rebac, _user("alice"), "doc-1", vector_store)
    assert vector_store.ownership_checked is True


@pytest.mark.asyncio
async def test_non_admin_non_owner_is_refused() -> None:
    rebac = _FakeRebac(is_platform_admin=False)
    vector_store = _FakeVectorStore(owns_document=False)
    with pytest.raises(AuthorizationError):
        await _authorize_fast_ingest_delete(rebac, _user("mallory"), "doc-1", vector_store)
    assert vector_store.ownership_checked is True
