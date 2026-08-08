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
`DocumentExtractor` (DOCREAD-01 Phase 2) — the exhaustive map-reduce that powers
server-side extraction. Covers: parse/NONE handling, exhaustive concat +
case-insensitive de-dupe across chunks (the whole point vs. the lossy
summarizer), rate-limit detection, and the 429 retry/backoff that lets a
throttling provider slow the map down instead of failing the turn.
"""

from __future__ import annotations

import pytest

from knowledge_flow_backend.features.extract import extractor as extractor_mod
from knowledge_flow_backend.features.extract.extractor import (
    DocumentExtractor,
    _is_rate_limit,
    _pack_windows,
    _parse_items,
)


class _AIMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeSplitter:
    """Splits on a sentinel so tests control chunk boundaries precisely."""

    def split(self, doc):
        from langchain_core.documents import Document

        parts = (doc.page_content or "").split("|||")
        return [Document(page_content=p, metadata={}) for p in parts]


class _FakeModel:
    """Returns a canned output per chunk (keyed by call order); can raise a
    rate-limit error a fixed number of times before succeeding."""

    def __init__(self, outputs: list[str], rate_limit_times: int = 0) -> None:
        self._outputs = outputs
        self._rate_limit_times = rate_limit_times
        self.calls = 0

    async def ainvoke(self, messages):
        if self._rate_limit_times > 0:
            self._rate_limit_times -= 1
            raise _RateLimitError()
        out = self._outputs[self.calls] if self.calls < len(self._outputs) else "NONE"
        self.calls += 1
        return _AIMessage(out)


class _RateLimitError(Exception):
    status_code = 429

    def __init__(self) -> None:
        super().__init__("Error 429: rate_limited")


def _make_extractor(model: _FakeModel) -> DocumentExtractor:
    ex = DocumentExtractor.__new__(DocumentExtractor)  # bypass ApplicationContext
    ex.context = None
    ex.model = model
    ex.splitter = _FakeSplitter()
    return ex


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_parse_items_strips_bullets_and_drops_none() -> None:
    assert _parse_items("- a\n* b\n1. c\n2) d") == ["a", "b", "c", "d"]
    assert _parse_items("NONE") == []
    assert _parse_items("  \n- keep\n\n") == ["keep"]


def test_is_rate_limit_detects_shapes() -> None:
    assert _is_rate_limit(_RateLimitError())[0] is True
    assert _is_rate_limit(ValueError("boom"))[0] is False


def test_pack_windows_reduces_call_count() -> None:
    # Ten 1k shards packed into ~2.5k windows → far fewer map calls than shards.
    shards = ["x" * 1000] * 10
    windows = _pack_windows(shards, 2500)
    assert len(windows) == 5  # 2 shards per window (3rd would exceed 2500)
    # A single oversized shard still becomes its own window (never dropped).
    assert _pack_windows(["y" * 9000], 2500) == ["y" * 9000]


# ---------------------------------------------------------------------------
# Exhaustive map-reduce
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_is_exhaustive_and_dedupes_across_chunks(monkeypatch) -> None:
    # Force one window per shard so the two shards make two map calls (with the
    # default 24k window they would pack into one). "req B" appears in both →
    # must appear once, order preserved.
    monkeypatch.setattr(extractor_mod, "_MAP_WINDOW_CHARS", 1)
    model = _FakeModel(["- req A\n- req B", "- req B\n- req C"])
    ex = _make_extractor(model)

    result = await ex.extract(text="chunk1|||chunk2", instruction="requirements")

    assert result.chunks_processed == 2  # two windows
    assert result.item_count == 3
    assert result.text == "- req A\n- req B\n- req C"


@pytest.mark.asyncio
async def test_extract_handles_all_none() -> None:
    model = _FakeModel(["NONE", "NONE"])
    ex = _make_extractor(model)
    result = await ex.extract(text="a|||b", instruction="penalties")
    assert result.item_count == 0
    assert result.text == ""


@pytest.mark.asyncio
async def test_extract_retries_on_rate_limit_then_succeeds(monkeypatch) -> None:
    # No real sleeping in the backoff.
    async def _no_sleep(_):
        return None

    monkeypatch.setattr(extractor_mod.asyncio, "sleep", _no_sleep)

    # Single chunk; model 429s twice, then returns the items.
    model = _FakeModel(["- only item"], rate_limit_times=2)
    ex = _make_extractor(model)

    result = await ex.extract(text="just one chunk", instruction="x")

    assert result.item_count == 1
    assert result.text == "- only item"
    # 2 failed attempts + 1 success.
    assert model.calls == 1


@pytest.mark.asyncio
async def test_extract_empty_input() -> None:
    ex = _make_extractor(_FakeModel([]))
    result = await ex.extract(text="   ", instruction="x")
    assert result.item_count == 0 and result.chunks_processed == 0
