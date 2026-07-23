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


import tempfile
from pathlib import Path

import pytest

from knowledge_flow_backend.core.processors.input.csv_tabular_processor.csv_tabular_processor import CsvTabularProcessor


def test_valid_csv():
    processor = CsvTabularProcessor()
    content = "name,age\nAlice,30\nBob,25"
    with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".csv") as f:
        f.write(content)
        temp_path = Path(f.name)

    assert processor.check_file_validity(temp_path)
    preview = processor.render_markdown_preview(temp_path, max_rows=20, max_cols=10)
    assert "name" in preview
    assert "age" in preview
    assert "Alice" in preview
    assert "30" in preview

    metadata = processor.extract_file_metadata(temp_path)
    assert metadata["num_columns"] == 2
    assert metadata["sample_columns"] == ["name", "age"]

    temp_path.unlink()


def test_inspect_read_options_returns_first_supported_non_utf8_encoding():
    processor = CsvTabularProcessor()
    content = "ville;montant\nMálaga;10\nLyon;25\n"
    with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".csv", encoding="latin1") as f:
        f.write(content)
        temp_path = Path(f.name)
    try:
        options = processor.inspect_read_options(temp_path)
        assert options.delimiter == ";"
        assert options.encoding == "CP1252"
    finally:
        temp_path.unlink()


def test_render_markdown_preview_marks_truncation(tmp_path):
    processor = CsvTabularProcessor()
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("name,age,city\nAlice,30,Paris\nBob,25,Lyon\n", encoding="utf-8")

    preview = processor.render_markdown_preview(csv_path, max_rows=1, max_cols=2)

    assert "name" in preview
    assert "age" in preview
    assert "Alice" in preview
    assert "30" in preview
    assert "city" not in preview
    assert "table truncated" in preview


def test_render_markdown_preview_escapes_pipe_characters(tmp_path):
    processor = CsvTabularProcessor()
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("name,notes\nAlice,a|b\n", encoding="utf-8")

    preview = processor.render_markdown_preview(csv_path, max_rows=5, max_cols=5)

    assert "a&#124;b" in preview


def test_inspect_read_options_rejects_invalid_csv_path(tmp_path):
    processor = CsvTabularProcessor()

    with pytest.raises(ValueError, match="File invalid or not found"):
        processor.inspect_read_options(tmp_path / "missing.csv")


def test_ragged_semicolon_export_is_tolerated(tmp_path):
    """Real-world Jira-style export: multi-line quoted fields with embedded
    delimiters/newlines plus a malformed trailing line. DuckDB's strict sniffer
    rejects this outright; the processor must skip only the broken row."""
    processor = CsvTabularProcessor()
    csv_path = tmp_path / "jira.csv"
    csv_path.write_text(
        'Résumé;Clé;Description\nx1;PHRS-1;"panel:\nligne;avec;points-virgules"\nx2;PHRS-2;ok\nligne-cassée\n',
        encoding="utf-8",
    )

    options = processor.inspect_read_options(csv_path)
    assert options.delimiter == ";"
    assert options.encoding == "utf-8"

    metadata = processor.extract_file_metadata(csv_path)
    assert metadata["num_columns"] == 3
    assert metadata["sample_columns"] == ["Résumé", "Clé", "Description"]
