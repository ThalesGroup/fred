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

"""#2150 — `_check_quota_before_upload` must not be bypassable.

The guard used to `return` immediately when `tags` was empty, and `tags` is the
request default, so omitting tags skipped storage quota entirely. It also read
the personal counter inside a bare `except Exception: current = 0`, turning any
transient store error into a second bypass.

These drive the real controller method with fake stores and assert on accept vs
reject, which is what the issue's acceptance criteria are stated in terms of.
"""

from types import SimpleNamespace
from uuid import uuid4

import fred_core
import pytest
from fastapi import HTTPException

from knowledge_flow_backend.features.ingestion import ingestion_controller as controller_module
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController

PERSONAL_LIMIT = 10_000


def _user(uid: str) -> fred_core.KeycloakUser:
    return fred_core.KeycloakUser(uid=uid, username=uid, email=f"{uid}@localhost", roles=["user"])


class _File:
    """Stands in for `UploadFile`; `size` may be absent, which the guard handles
    by seeking to the end of the stream."""

    def __init__(self, size: int | None, *, stream_size: int | None = None):
        self.size = size
        self._stream_size = stream_size if stream_size is not None else (size or 0)
        self.file = _Stream(self._stream_size)


class _Stream:
    def __init__(self, size: int):
        self._size = size
        self.pos = 0

    def seek(self, offset: int, whence: int = 0) -> None:
        self.pos = self._size if whence == 2 else offset

    def tell(self) -> int:
        return self.pos


def _install(monkeypatch, *, current_usage: int, personal_limit: int | None = PERSONAL_LIMIT, read_raises: bool = False):
    class _FakeUserStore:
        async def find_user_by_id(self, user_uuid):
            if read_raises:
                raise RuntimeError("postgres unavailable")
            return SimpleNamespace(current_resources_storage_size=current_usage)

    monkeypatch.setattr(controller_module, "get_user_store", lambda: _FakeUserStore(), raising=False)
    # `_check_quota_before_upload` imports `get_user_store` from `fred_core`
    # inside the function body, so the patch has to land on the module object.
    monkeypatch.setattr(fred_core, "get_user_store", lambda: _FakeUserStore())

    cfg = SimpleNamespace(app=SimpleNamespace(personal_max_resources_storage_size=personal_limit, default_team_max_resources_storage_size=None))
    monkeypatch.setattr(
        controller_module.ApplicationContext,
        "get_instance",
        staticmethod(lambda: SimpleNamespace(get_config=lambda: cfg)),
    )


def _controller(monkeypatch, *, team_ids=None, user_ids=None):
    ctrl = IngestionController.__new__(IngestionController)

    async def _fake_resolve(tags, user):
        return set(team_ids or []), set(user_ids or [])

    ctrl._resolve_tag_owners = _fake_resolve  # type: ignore[method-assign]
    return ctrl


@pytest.mark.asyncio
async def test_tagless_upload_within_personal_quota_is_accepted(monkeypatch) -> None:
    """AC1 — a tagless upload under the personal limit still goes through."""
    _install(monkeypatch, current_usage=1_000)
    ctrl = _controller(monkeypatch)
    await ctrl._check_quota_before_upload([_File(2_000)], [], _user(str(uuid4())))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_tagless_upload_over_personal_quota_is_rejected(monkeypatch) -> None:
    """AC2 — the bypass itself: before the fix this returned early and accepted
    an upload of any size, because `tags` defaults to `[]`."""
    _install(monkeypatch, current_usage=9_000)
    ctrl = _controller(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await ctrl._check_quota_before_upload([_File(2_000)], [], _user(str(uuid4())))  # type: ignore[arg-type]
    assert exc.value.status_code == 400
    assert "quota exceeded" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_tagged_upload_still_resolves_its_tag_owners(monkeypatch) -> None:
    """AC3 — tagged uploads keep the existing behaviour: the check follows the
    tag's owner, not the uploader, so the tagless fallback must not hijack it."""
    _install(monkeypatch, current_usage=9_000)
    seen: list[str] = []

    ctrl = IngestionController.__new__(IngestionController)

    async def _fake_resolve(tags, user):
        seen.extend(tags)
        return set(), {str(uuid4())}  # a personal-owned tag, owner != uploader

    ctrl._resolve_tag_owners = _fake_resolve  # type: ignore[method-assign]

    with pytest.raises(HTTPException):
        await ctrl._check_quota_before_upload([_File(2_000)], ["tag-a"], _user(str(uuid4())))  # type: ignore[arg-type]
    assert seen == ["tag-a"]


@pytest.mark.asyncio
async def test_upload_size_is_measured_when_the_file_reports_no_size(monkeypatch) -> None:
    """AC4 — both size branches. With `size=None` the guard measures the stream,
    so an over-quota upload is still rejected rather than counted as 0 bytes."""
    _install(monkeypatch, current_usage=9_000)
    ctrl = _controller(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await ctrl._check_quota_before_upload([_File(None, stream_size=2_000)], [], _user(str(uuid4())))  # type: ignore[arg-type]
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_an_unreadable_counter_rejects_instead_of_assuming_zero(monkeypatch) -> None:
    """The guard must fail CLOSED. Treating a store error as `current = 0` let a
    user at 90% of quota upload anything at all during a transient blip."""
    _install(monkeypatch, current_usage=9_000, read_raises=True)
    ctrl = _controller(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await ctrl._check_quota_before_upload([_File(2_000)], [], _user(str(uuid4())))  # type: ignore[arg-type]
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_no_personal_limit_configured_leaves_uploads_unrestricted(monkeypatch) -> None:
    """Regression guard: the tagless fallback must not invent a limit where the
    deployment configured none."""
    _install(monkeypatch, current_usage=10**9, personal_limit=None)
    ctrl = _controller(monkeypatch)
    await ctrl._check_quota_before_upload([_File(2_000)], [], _user(str(uuid4())))  # type: ignore[arg-type]
