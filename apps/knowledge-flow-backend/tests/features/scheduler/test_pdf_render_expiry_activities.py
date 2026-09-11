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

"""The nightly render expiry activity, run against a fake content store."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from knowledge_flow_backend.core.stores.content.base_content_store import StoredObjectInfo
from knowledge_flow_backend.features.scheduler.pdf_render_expiry_activities import (
    PDF_RENDER_EXPIRED_TOTAL,
    expire_pdf_renders,
)

_PATCH_CTX = "knowledge_flow_backend.application_context.ApplicationContext.get_instance"
_NOW = datetime.now(timezone.utc)


def _render(document_uid: str, age_days: float | None) -> StoredObjectInfo:
    modified = None if age_days is None else _NOW - timedelta(days=age_days)
    return StoredObjectInfo(
        key=f"{document_uid}/output/render.pdf",
        size=10,
        file_name="render.pdf",
        modified=modified,
        document_uid=document_uid,
    )


class _FakeStore:
    def __init__(self, renders: list[StoredObjectInfo], *, failing: set[str] = frozenset(), list_error: Exception | None = None) -> None:
        self._renders = renders
        self._failing = failing
        self._list_error = list_error
        self.deleted: list[str] = []
        self.list_calls = 0

    def list_output_artifacts(self, artifact_name: str) -> list[StoredObjectInfo]:
        self.list_calls += 1
        assert artifact_name == "render.pdf"
        if self._list_error is not None:
            raise self._list_error
        return list(self._renders)

    def delete_output_artifact(self, doc_path: str) -> None:
        if doc_path in self._failing:
            raise RuntimeError(f"cannot delete {doc_path}")
        self.deleted.append(doc_path)


def _context(store: _FakeStore, ttl_days: int = 30) -> tuple[MagicMock, MagicMock]:
    kpi = MagicMock()
    ctx = MagicMock()
    ctx.get_config.return_value = SimpleNamespace(app=SimpleNamespace(pdf_render_ttl_days=ttl_days))
    ctx.get_content_store.return_value = store
    ctx.get_kpi_writer.return_value = kpi
    return ctx, kpi


def _run(ctx) -> dict:
    with patch(_PATCH_CTX, return_value=ctx):
        return asyncio.run(expire_pdf_renders())


def test_deletes_only_renders_older_than_the_ttl() -> None:
    store = _FakeStore([_render("fresh", 1), _render("boundary", 29.9), _render("old", 31), _render("older", 400), _render("undated", None)])
    ctx, kpi = _context(store)

    result = _run(ctx)

    assert store.deleted == ["old/output/render.pdf", "older/output/render.pdf"]
    assert result == {"ttl_days": 30, "scanned": 5, "expired": 2, "failed": 0}
    kpi.count.assert_called_once()
    name, inc = kpi.count.call_args.args
    assert (name, inc, kpi.count.call_args.kwargs["dims"]) == (PDF_RENDER_EXPIRED_TOTAL, 2, {"status": "ok"})


def test_ttl_change_is_picked_up_from_configuration() -> None:
    store = _FakeStore([_render("a", 31), _render("b", 61)])
    ctx, _ = _context(store, ttl_days=60)

    result = _run(ctx)

    assert store.deleted == ["b/output/render.pdf"]
    assert result["ttl_days"] == 60


def test_ttl_zero_does_not_touch_the_store() -> None:
    store = _FakeStore([_render("old", 400)])
    ctx, kpi = _context(store, ttl_days=0)

    result = _run(ctx)

    assert result == {"ttl_days": 0, "scanned": 0, "expired": 0, "failed": 0}
    assert store.list_calls == 0 and store.deleted == []
    kpi.count.assert_not_called()


def test_one_failed_deletion_does_not_stop_the_pass() -> None:
    store = _FakeStore([_render("a", 40), _render("b", 40), _render("c", 40)], failing={"b/output/render.pdf"})
    ctx, kpi = _context(store)

    result = _run(ctx)

    assert store.deleted == ["a/output/render.pdf", "c/output/render.pdf"]
    assert (result["expired"], result["failed"]) == (2, 1)
    statuses = [(call.args[1], call.kwargs["dims"]["status"]) for call in kpi.count.call_args_list]
    assert statuses == [(2, "ok"), (1, "error")]


def test_listing_failure_raises_so_temporal_retries() -> None:
    store = _FakeStore([], list_error=RuntimeError("bucket unreachable"))
    ctx, _ = _context(store)

    with pytest.raises(RuntimeError, match="bucket unreachable"):
        _run(ctx)
    assert store.deleted == []


def test_naive_modified_timestamps_are_read_as_utc() -> None:
    naive_old = _render("naive", None)
    naive_old.modified = (_NOW - timedelta(days=45)).replace(tzinfo=None)
    store = _FakeStore([naive_old])
    ctx, _ = _context(store)

    _run(ctx)

    assert store.deleted == ["naive/output/render.pdf"]
