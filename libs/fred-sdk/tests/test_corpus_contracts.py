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
Offline unit tests for the indexed corpus contract (CORPUS-01, draft).

Tests cover:
- Corpus / CorpusScope construction and validation
- the push/pull <-> connector_kind/connector_ref exclusivity invariant (RFC §2/§7)
- SourceItem / SourceChange construction
- a minimal in-memory fake proving SourceConnector is actually implementable

All tests run without any external services.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fred_sdk.contracts.connector import ChangeKind, SourceChange, SourceItem
from fred_sdk.contracts.corpus import Corpus, CorpusKind, CorpusMode, CorpusScope

# ---------------------------------------------------------------------------
# CorpusScope / Corpus
# ---------------------------------------------------------------------------


def test_corpus_scope_requires_team_id() -> None:
    with pytest.raises(Exception):
        CorpusScope(team_id="")  # type: ignore[call-arg]


def test_corpus_scope_defaults_to_no_tags() -> None:
    scope = CorpusScope(team_id="team-1")
    assert scope.tag_ids == []


def test_push_corpus_requires_no_connector_fields() -> None:
    corpus = Corpus(
        corpus_id="c-1",
        name="Team RAG corpus",
        scope=CorpusScope(team_id="team-1"),
        mode=CorpusMode.PUSH,
        kind=CorpusKind.RAG_SQL,
    )
    assert corpus.connector_kind is None
    assert corpus.connector_ref is None


def test_push_corpus_rejects_connector_ref() -> None:
    with pytest.raises(Exception):
        Corpus(
            corpus_id="c-1",
            name="Team RAG corpus",
            scope=CorpusScope(team_id="team-1"),
            mode=CorpusMode.PUSH,
            kind=CorpusKind.RAG_SQL,
            connector_ref="conn-1",
        )


def test_pull_corpus_requires_both_connector_fields() -> None:
    with pytest.raises(Exception):
        Corpus(
            corpus_id="c-2",
            name="Team pull corpus",
            scope=CorpusScope(team_id="team-1"),
            mode=CorpusMode.PULL,
            kind=CorpusKind.RAG_SQL,
        )


def test_pull_corpus_rejects_connector_ref_without_kind() -> None:
    with pytest.raises(Exception):
        Corpus(
            corpus_id="c-2",
            name="Team pull corpus",
            scope=CorpusScope(team_id="team-1"),
            mode=CorpusMode.PULL,
            kind=CorpusKind.RAG_SQL,
            connector_ref="conn-1",
        )


def test_pull_corpus_rejects_connector_kind_without_ref() -> None:
    with pytest.raises(Exception):
        Corpus(
            corpus_id="c-2",
            name="Team pull corpus",
            scope=CorpusScope(team_id="team-1"),
            mode=CorpusMode.PULL,
            kind=CorpusKind.RAG_SQL,
            connector_kind="local_fs",
        )


def test_pull_corpus_with_both_connector_fields_is_valid() -> None:
    corpus = Corpus(
        corpus_id="c-2",
        name="Team pull corpus",
        scope=CorpusScope(team_id="team-1", tag_ids=["tag-a"]),
        mode=CorpusMode.PULL,
        kind=CorpusKind.RAG_SQL,
        connector_kind="local_fs",
        connector_ref="conn-1",
    )
    assert corpus.connector_kind == "local_fs"
    assert corpus.connector_ref == "conn-1"
    assert corpus.scope.tag_ids == ["tag-a"]


def test_corpus_is_frozen() -> None:
    corpus = Corpus(
        corpus_id="c-1",
        name="Team RAG corpus",
        scope=CorpusScope(team_id="team-1"),
        mode=CorpusMode.PUSH,
        kind=CorpusKind.RAG_SQL,
    )
    with pytest.raises(Exception):
        corpus.name = "renamed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SourceItem / SourceChange
# ---------------------------------------------------------------------------


def test_source_item_requires_stable_identity_and_revision() -> None:
    with pytest.raises(Exception):
        SourceItem(source_item_id="", revision="rev-1", display_path="a/b.pdf")  # type: ignore[call-arg]
    with pytest.raises(Exception):
        SourceItem(source_item_id="id-1", revision="", display_path="a/b.pdf")  # type: ignore[call-arg]


def test_source_change_upsert_and_delete() -> None:
    item = SourceItem(source_item_id="id-1", revision="rev-1", display_path="a/b.pdf")
    upsert = SourceChange(item=item, kind=ChangeKind.UPSERT)
    delete = SourceChange(item=item, kind=ChangeKind.DELETE)
    assert upsert.kind is ChangeKind.UPSERT
    assert delete.kind is ChangeKind.DELETE


# ---------------------------------------------------------------------------
# SourceConnector — prove the Protocol is actually implementable
# ---------------------------------------------------------------------------


class _FakeConnector:
    """Minimal in-memory connector: one item, one change, no real I/O."""

    def __init__(self) -> None:
        self._item = SourceItem(
            source_item_id="id-1", revision="rev-1", display_path="a/b.pdf"
        )

    def discover_changes(self, cursor: str | None) -> tuple[list[SourceChange], str]:
        if cursor == "done":
            return [], "done"
        return [SourceChange(item=self._item, kind=ChangeKind.UPSERT)], "done"

    def fetch(self, item: SourceItem, destination_dir: Path) -> Path:
        destination_dir.mkdir(parents=True, exist_ok=True)
        local_path = destination_dir / item.display_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text("fake content")
        return local_path


def test_fake_connector_satisfies_source_connector_protocol(tmp_path: Path) -> None:
    connector = _FakeConnector()

    changes, cursor = connector.discover_changes(None)
    assert len(changes) == 1
    assert cursor == "done"

    fetched = connector.fetch(changes[0].item, tmp_path)
    assert fetched.exists()
    assert fetched.read_text() == "fake content"

    changes_again, _ = connector.discover_changes(cursor)
    assert changes_again == []
