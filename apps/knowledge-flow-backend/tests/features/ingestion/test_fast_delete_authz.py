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
- a non-admin non-owner is refused;
- a document with no chunks at all is allowed (idempotent no-op), so a retry
  after an earlier attempt already deleted the vectors but failed on a later
  cleanup step can still converge.
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
    """Records the delete-authorization check the authorizer makes, including
    the exact user_id it was asked to check -- a wrong-identifier bug (e.g.
    forwarding username instead of uid) would otherwise still pass these tests."""

    def __init__(self, *, may_delete: bool) -> None:
        self._may_delete = may_delete
        self.checked = False
        self.checked_user_id: str | None = None

    def may_delete_session_document(self, document_uid: str, user_id: str) -> bool:
        self.checked = True
        self.checked_user_id = user_id
        assert document_uid == "doc-1"
        return self._may_delete


@pytest.mark.asyncio
async def test_platform_admin_bypasses_document_ownership() -> None:
    rebac = _FakeRebac(is_platform_admin=True)
    vector_store = _FakeVectorStore(may_delete=False)
    # Admin: allowed even though it owns nothing, and the ownership check is skipped.
    await _authorize_fast_ingest_delete(rebac, _user(), "doc-1", vector_store)
    assert vector_store.checked is False


@pytest.mark.asyncio
async def test_non_admin_owner_passes_ownership_check() -> None:
    rebac = _FakeRebac(is_platform_admin=False)
    vector_store = _FakeVectorStore(may_delete=True)
    await _authorize_fast_ingest_delete(rebac, _user("alice"), "doc-1", vector_store)
    assert vector_store.checked is True
    assert vector_store.checked_user_id == "alice"


@pytest.mark.asyncio
async def test_non_admin_non_owner_is_refused() -> None:
    rebac = _FakeRebac(is_platform_admin=False)
    vector_store = _FakeVectorStore(may_delete=False)
    with pytest.raises(AuthorizationError):
        await _authorize_fast_ingest_delete(rebac, _user("mallory"), "doc-1", vector_store)
    assert vector_store.checked is True
    assert vector_store.checked_user_id == "mallory"


@pytest.mark.asyncio
async def test_retry_after_vectors_already_deleted_converges() -> None:
    """A retry that reaches this check after an earlier attempt already deleted
    every chunk (but failed on a later cleanup step) must not be denied forever
    just because there is nothing left to prove ownership over."""
    rebac = _FakeRebac(is_platform_admin=False)
    vector_store = _FakeVectorStore(may_delete=True)
    await _authorize_fast_ingest_delete(rebac, _user("alice"), "doc-1", vector_store)
    assert vector_store.checked is True
