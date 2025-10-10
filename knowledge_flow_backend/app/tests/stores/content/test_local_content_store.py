# Copyright Thales 2025
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

# pylint: disable=redefined-outer-name

"""
Test suite for the LocalStorageBackend class in local_content_store.py.

This test module covers:
- Normal cases: saving, retrieving, and deleting document content and markdown.
- Error cases: missing input/output folders, empty input, file read failures.
- Edge cases: overwriting existing content, deleting non-existent content.
- Logging behaviors and file operations.

All tests are isolated using pytest's tmp_path and monkeypatch fixtures.
"""

from pathlib import Path

import pytest

from app.core.stores.content.filesystem_content_store import FileSystemContentStore

# ----------------------------
# ⚙️ Fixtures
# ----------------------------


@pytest.fixture
def tmp_store(tmp_path):
    """Provide a temporary local storage backend."""
    return FileSystemContentStore(document_root=tmp_path / "documents", object_root=tmp_path / "objects")


# ----------------------------
# ✅ Nominal Cases
# ----------------------------


def test_save_and_get_content(tmp_store, tmp_path):
    """Save and get file content."""
    doc_id = "doc1"
    doc_dir = tmp_path / "source"
    input_dir = doc_dir / "input"
    input_dir.mkdir(parents=True)
    file_path = input_dir / "test.txt"
    file_path.write_bytes(b"Hello")

    tmp_store.save_content(doc_id, doc_dir)
    content = tmp_store.get_content(doc_id)
    assert content.read() == b"Hello"
    content.close()


def test_save_and_get_markdown(tmp_store, tmp_path):
    """Save and read a markdown file."""
    doc_id = "doc2"
    doc_dir = tmp_path / "source2"
    output_dir = doc_dir / "output"
    output_dir.mkdir(parents=True)
    md_file = output_dir / "output.md"
    md_file.write_text("# Hello")

    tmp_store.save_content(doc_id, doc_dir)
    markdown = tmp_store.get_markdown(doc_id)
    assert markdown == "# Hello"


def test_save_content_overwrites_existing_directory(tmp_store, tmp_path):
    """Make sure the target directory is removed before processing save_content."""
    doc_id = "doc5"
    doc_dir = tmp_path / "source5"
    doc_dir.mkdir()
    (doc_dir / "input").mkdir()
    (doc_dir / "input" / "file1.txt").write_text("new content")
    dest_path = tmp_store.destination_root / doc_id
    dest_path.mkdir(parents=True)
    old_file = dest_path / "old.txt"
    old_file.write_text("old content")
    assert old_file.exists()
    tmp_store.save_content(doc_id, doc_dir)
    assert not old_file.exists()
    new_file = dest_path / "input" / "file1.txt"
    assert new_file.exists()
    assert new_file.read_text() == "new content"


def test_delete_content(tmp_store, tmp_path):
    """Delete a file content."""
    doc_id = "doc4"
    doc_dir = tmp_path / "source4"
    doc_dir.mkdir()
    tmp_store.save_content(doc_id, doc_dir)
    tmp_store.delete_content(doc_id)
    assert not (tmp_store.destination_root / doc_id).exists()


# ----------------------------
# ❌ Failure Cases
# ----------------------------


def test_get_content_file_not_found(tmp_store):
    """Raise FileNotFoundError if the folder does not exist."""
    with pytest.raises(FileNotFoundError):
        tmp_store.get_content("missing_doc")


def test_get_content_empty_input(tmp_store, tmp_path):
    """Raise FileNotFoundError if the folder is empty."""
    doc_id = "doc3"
    doc_dir = tmp_path / "source3"
    (doc_dir / "input").mkdir(parents=True)
    tmp_store.save_content(doc_id, doc_dir)

    dest = tmp_store.destination_root / doc_id / "input"
    for f in dest.iterdir():
        f.unlink()

    with pytest.raises(FileNotFoundError):
        tmp_store.get_content(doc_id)


def test_get_markdown_not_found(tmp_store):
    """Raise FileNotFoundError if the markdown file is missing."""
    with pytest.raises(FileNotFoundError):
        tmp_store.get_markdown("unknown_doc")


def test_save_content_copies_file_and_logs(tmp_store, tmp_path, caplog):
    """Ensure save_content copies a file and logs the file copy message."""
    doc_id = "doc_file_copy"
    doc_dir = tmp_path / "source_file"
    doc_dir.mkdir()
    file = doc_dir / "example.txt"
    file.write_text("some data")
    with caplog.at_level("INFO"):
        tmp_store.save_content(doc_id, doc_dir)
    copied_file = tmp_store.destination_root / doc_id / "example.txt"
    assert copied_file.exists()
    assert copied_file.read_text() == "some data"
    assert any("Copied file" in msg for msg in caplog.text.splitlines())


def test_get_markdown_raises_and_logs(monkeypatch, tmp_store, tmp_path, caplog):
    """get_markdown logs and raises if reading output.md fails unexpectedly."""
    doc_id = "doc_md_error"
    doc_dir = tmp_path / "source_md_error"
    output_dir = doc_dir / "output"
    output_dir.mkdir(parents=True)
    md_file = output_dir / "output.md"
    md_file.write_text("valid content")
    tmp_store.save_content(doc_id, doc_dir)
    target_md_path = tmp_store.destination_root / doc_id / "output" / "output.md"
    original_read_text = Path.read_text

    def faulty_read_text(self, *args, **kwargs):
        if self == target_md_path:
            raise OSError("Read error")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", faulty_read_text)
    with caplog.at_level("ERROR"):
        with pytest.raises(OSError, match="Read error"):
            tmp_store.get_markdown(doc_id)
    assert "Error reading markdown file" in caplog.text


# ----------------------------
# ⚠️ Edge Cases
# ----------------------------


def test_delete_nonexistent_content(tmp_store):
    """Delete the content if the file does not exists."""
    tmp_store.delete_content("nonexistent_doc")
