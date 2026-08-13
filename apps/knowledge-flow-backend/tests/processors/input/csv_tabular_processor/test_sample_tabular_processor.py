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


import logging
import tempfile
from pathlib import Path

import duckdb
import pytest

from knowledge_flow_backend.core.processors.input.csv_tabular_processor.csv_tabular_processor import (
    CsvReadOptions,
    CsvTabularProcessor,
)


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


def test_inspect_read_options_logs_when_utf8_fallback_also_fails(tmp_path, caplog, monkeypatch):
    """The UTF-8-transcode fallback is the terminal attempt: when it also fails,
    the failure must be logged, not just re-raised. Otherwise an operator watching
    stdout only sees the two earlier warnings and a bare error propagating out —
    the actual root cause is only visible in the HTTP error response reaching the
    end user, never in the backend's own logs."""
    processor = CsvTabularProcessor()
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")

    def always_fail(self, path, *, delimiter, encoding):
        raise duckdb.Error("boom")

    monkeypatch.setattr(CsvTabularProcessor, "_validate_duckdb_read", always_fail)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(duckdb.Error, match="boom"):
            processor.inspect_read_options(csv_path)

    assert any("after transcoding to UTF-8" in record.message for record in caplog.records)


# Verbatim excerpt from a real semicolon-delimited export (issue #2366's
# export-exigences.csv) — bisected down to the shortest prefix that reliably
# breaks csv.Sniffer, then closed into a syntactically complete CSV. The
# embedded raw '\n' inside the first quoted field (before its closing quote)
# is what throws the sniffer off, well before it sees enough consistent rows
# to settle on ';'.
_UNSNIFFABLE_SEMICOLON_EXPORT = (
    "REQ_ID;REQ_VERSION_NAME;REQ_VERSION_DESCRIPTION\n"
    '1943;Ajout .zip dans les upload de fichier;"les fichier de types ZIP sont autorisés\xa0\n"\n'
    '1106;Comportement de recherche dans un champ liste;"A partir du moment ou un champ de type liste '
    "(donc liste à choix unique ou à selection multiple) contient 5 éléments, une barre de recherche "
    "permettant à l'utilisateur de rechercher les éléments de la liste apparaît.\n\"\n"
    "1847;Conditionner l'affichage de l'éditeur de texte par champs;\"Composant permetant de :d'écrire"
    "\xa0de long texte sans pour autant avoir un éditeur de texte dans le champ.de visualiser de long texte "
    'sans pour autant avoir un éditeur de texte dans le champ.\n"\n'
    "1549;Emplacement de defaut_value dans FORMULAIRE;\"Quand\xa0 l'administrateur est dans le menu "
    '""Gére les champs""\xa0\n"\n'
    "99;ok;fin\n"
)


def test_detect_delimiter_returns_none_when_sniffing_fails(tmp_path):
    """A quoted field with an embedded raw newline (real-world export
    artifact, e.g. issue #2366's export-exigences.csv) can throw off
    csv.Sniffer before it sees enough consistent rows to settle on a
    delimiter. detect_delimiter must return None rather than silently
    defaulting to ',' — a wrong guess forces DuckDB to look for a delimiter
    that isn't actually there."""
    processor = CsvTabularProcessor()
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(_UNSNIFFABLE_SEMICOLON_EXPORT, encoding="utf-8")

    assert processor.detect_delimiter(csv_path, ["utf-8"]) is None


def test_build_duckdb_read_relation_sql_omits_delim_when_unset():
    """When our own sniff couldn't settle on a delimiter (CsvReadOptions.delimiter
    is None), the generated SQL must not pass `delim=` at all — DuckDB's own
    read_csv_auto then runs its full built-in auto-detection instead of being
    constrained to a forced (and possibly wrong) single candidate."""
    processor = CsvTabularProcessor()
    options = CsvReadOptions(delimiter=None, encoding="utf-8", header=True)

    sql = processor.build_duckdb_read_relation_sql(Path("/tmp/input.csv"), options)

    assert "delim=" not in sql
    assert "encoding='utf-8'" in sql


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
