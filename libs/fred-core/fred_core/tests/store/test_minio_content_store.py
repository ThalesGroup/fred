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

"""Unit tests for MinioContentStore presigned URLs using a fake client (no network)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
from fred_core.store import minio_content_store
from fred_core.store.minio_content_store import (
    MinioContentStore,
    _stable_signing_date,
)
from minio import Minio


class _FakePublicClient:
    """Records the arguments the store passes to `presigned_get_object`."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def presigned_get_object(self, bucket_name, object_name, **kwargs):
        self.calls.append({"bucket": bucket_name, "object": object_name, **kwargs})
        date = kwargs["request_date"]
        headers = kwargs["response_headers"]
        return f"https://minio.test/{object_name}?date={date.isoformat()}&cc={headers['response-cache-control']}"


@pytest.fixture
def store() -> MinioContentStore:
    # The constructor opens two MinIO clients and creates the bucket; only the
    # presigning attributes matter here, so build the instance without running it.
    instance = MinioContentStore.__new__(MinioContentStore)
    instance.object_bucket = "control-plane-content-objects"
    instance.public_client = cast(Minio, _FakePublicClient())
    return instance


@pytest.fixture
def frozen_clock(monkeypatch):
    """Pin the module clock so anchoring never straddles a real window boundary."""

    def freeze(moment: datetime) -> None:
        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return moment

        monkeypatch.setattr(minio_content_store, "datetime", _FrozenDatetime)

    return freeze


def test_stable_signing_date_is_identical_across_a_window(frozen_clock) -> None:
    # A one-hour TTL gives a quarter-hour grid: 10:03 and 10:14 must anchor to
    # the same 10:00, so both calls mint the exact same URL.
    expires = timedelta(hours=1)
    frozen_clock(datetime(2026, 9, 29, 10, 3, 27, tzinfo=timezone.utc))
    early = _stable_signing_date(expires)
    frozen_clock(datetime(2026, 9, 29, 10, 14, 59, tzinfo=timezone.utc))
    late = _stable_signing_date(expires)

    assert early == late == datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)


def test_stable_signing_date_moves_to_the_next_window(frozen_clock) -> None:
    expires = timedelta(hours=1)
    frozen_clock(datetime(2026, 9, 29, 10, 14, 59, tzinfo=timezone.utc))
    before = _stable_signing_date(expires)
    frozen_clock(datetime(2026, 9, 29, 10, 15, 1, tzinfo=timezone.utc))
    after = _stable_signing_date(expires)

    assert before is not None
    assert after == before + timedelta(minutes=15)


def test_stable_signing_date_keeps_most_of_the_ttl(frozen_clock) -> None:
    # Worst case: anchoring backdates the signature by a full window, so the
    # minted URL still carries three quarters of the requested TTL.
    expires = timedelta(hours=1)
    now = datetime(2026, 9, 29, 10, 14, 59, tzinfo=timezone.utc)
    frozen_clock(now)
    anchored = _stable_signing_date(expires)

    assert anchored is not None
    remaining = anchored + expires - now
    assert remaining >= expires * 3 / 4


def test_stable_signing_date_returns_none_for_a_zero_ttl() -> None:
    assert _stable_signing_date(timedelta(0)) is None


def test_presigned_url_is_byte_identical_across_calls(store, frozen_clock) -> None:
    # Two bootstrap renders minutes apart must hand the browser the same URL,
    # otherwise the cached avatar can never be reused.
    frozen_clock(datetime(2026, 9, 29, 10, 3, 27, tzinfo=timezone.utc))
    first = store.get_presigned_url("teams/t1/avatar-abc.webp")
    frozen_clock(datetime(2026, 9, 29, 10, 14, 59, tzinfo=timezone.utc))
    second = store.get_presigned_url("teams/t1/avatar-abc.webp")

    assert first == second


def test_presigned_url_caches_for_exactly_one_signing_window(store) -> None:
    # A minted URL is only handed out until the window rolls over, so freshness
    # beyond that would overstate what the browser can actually reuse.
    store.get_presigned_url("teams/t1/avatar-abc.webp", expires=timedelta(hours=2))

    call = store.public_client.calls[0]
    assert call["response_headers"] == {
        "response-cache-control": "private, max-age=1800"
    }


def test_presigned_url_strips_the_leading_slash(store) -> None:
    store.get_presigned_url("/teams/t1/avatar-abc.webp")

    assert store.public_client.calls[0]["object"] == "teams/t1/avatar-abc.webp"


class _FakeWriteClient:
    """Mimics S3 `remove_object`, which succeeds whether or not the key exists."""

    def __init__(self, objects: set[str]) -> None:
        self.objects = objects
        self.removed: list[tuple[str, str]] = []

    def remove_object(self, bucket_name, object_name):
        self.removed.append((bucket_name, object_name))
        self.objects.discard(object_name)


def test_delete_object_removes_an_existing_object(store) -> None:
    client = _FakeWriteClient({"users/u1/avatar.png"})
    store.client = cast(Minio, client)

    store.delete_object("/users/u1/avatar.png")

    assert client.objects == set()
    assert client.removed == [("control-plane-content-objects", "users/u1/avatar.png")]


def test_delete_object_on_a_missing_object_is_a_no_op(store) -> None:
    client = _FakeWriteClient(set())
    store.client = cast(Minio, client)

    store.delete_object("users/u1/missing.png")

    assert client.removed == [("control-plane-content-objects", "users/u1/missing.png")]
