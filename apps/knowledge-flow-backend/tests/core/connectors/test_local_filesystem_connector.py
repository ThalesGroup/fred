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
Offline unit tests for LocalFilesystemConnector (docs/swift/rfc/INDEXED-CORPUS-RFC.md).

Covers the exact failure modes the connector contract was written against:
content-based change detection (not mtime), delete detection, and a stable
no-op when nothing changed. All tests run against a real temporary directory,
no mocks.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fred_sdk.contracts.connector import ChangeKind

from knowledge_flow_backend.core.connectors.local_filesystem_connector import LocalFilesystemConnector


def test_first_scan_reports_upsert_for_every_file(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("world")

    connector = LocalFilesystemConnector(tmp_path)
    changes, cursor = connector.discover_changes(None)

    paths = {c.item.display_path for c in changes}
    assert paths == {"a.txt", "sub/b.txt"}
    assert all(c.kind is ChangeKind.UPSERT for c in changes)
    assert cursor


def test_second_scan_with_no_change_reports_nothing(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello")
    connector = LocalFilesystemConnector(tmp_path)

    _, cursor = connector.discover_changes(None)
    changes_again, cursor_again = connector.discover_changes(cursor)

    assert changes_again == []
    assert cursor_again == cursor


def test_content_change_is_detected_even_with_same_mtime(tmp_path: Path) -> None:
    file_path = tmp_path / "a.txt"
    file_path.write_text("hello")
    connector = LocalFilesystemConnector(tmp_path)
    _, cursor = connector.discover_changes(None)

    file_path.write_text("goodbye")
    original_stat = file_path.stat()
    os.utime(file_path, (original_stat.st_atime, original_stat.st_mtime))

    changes, _ = connector.discover_changes(cursor)

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.UPSERT
    assert changes[0].item.display_path == "a.txt"


def test_deleted_file_is_reported(tmp_path: Path) -> None:
    file_path = tmp_path / "a.txt"
    file_path.write_text("hello")
    connector = LocalFilesystemConnector(tmp_path)
    _, cursor = connector.discover_changes(None)

    file_path.unlink()
    changes, _ = connector.discover_changes(cursor)

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.DELETE
    assert changes[0].item.display_path == "a.txt"


def test_fetch_copies_file_into_destination(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "a.txt").write_text("hello")
    connector = LocalFilesystemConnector(source_root)

    changes, _ = connector.discover_changes(None)
    destination_root = tmp_path / "destination"

    fetched = connector.fetch(changes[0].item, destination_root)

    assert fetched.read_text() == "hello"
    assert fetched == destination_root / "a.txt"


def test_constructor_rejects_non_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        LocalFilesystemConnector(tmp_path / "missing")
