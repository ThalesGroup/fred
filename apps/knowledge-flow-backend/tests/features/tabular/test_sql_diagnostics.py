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

"""SQL diagnostic candidates never escape the proven visible/mounted scope."""

from __future__ import annotations

import duckdb
import pytest

from knowledge_flow_backend.features.tabular.diagnostics import VisibleQueryRelation, scoped_column_diagnostic
from knowledge_flow_backend.features.tabular.utils import validate_read_query

_COLUMNS = {
    "Commandes": ["commande_id", "client_id", "devise"],
    "Clients": ["client_id", "region", "devise", "secret_internal_label"],
}


def _binder_failure(sql: str) -> str:
    """Get a real engine failure so tests follow DuckDB's supported wording."""

    connection = duckdb.connect(config={"threads": 1})
    try:
        connection.execute("CREATE TABLE Commandes (commande_id VARCHAR, client_id VARCHAR, devise VARCHAR)")
        connection.execute("CREATE TABLE Clients (client_id VARCHAR, region VARCHAR, devise VARCHAR, secret_internal_label VARCHAR)")
        with pytest.raises(duckdb.BinderException) as failure:
            connection.execute(sql)
        return str(failure.value)
    finally:
        connection.close()


def _diagnostic(sql: str) -> str:
    """Mirror the query boundary: only referenced, already mounted schemas."""

    validated = validate_read_query(sql, allowed_relations=_COLUMNS)
    return scoped_column_diagnostic(
        _binder_failure(sql),
        relations=validated.diagnostic_relations,
        mounted_columns={name: _COLUMNS[name] for name in validated.referenced_relations},
    )


def test_missing_column_only_shows_the_referenced_table() -> None:
    message = _diagnostic("SELECT c.region FROM Commandes c")

    assert 'Column "region" does not exist in "Commandes" (SQL qualifier "c")' in message
    assert '"c"."commande_id"' in message
    assert '"c"."client_id"' in message
    assert "Clients" not in message
    assert "secret_internal_label" not in message


def test_an_authorized_but_unreferenced_schema_is_ignored_even_if_passed() -> None:
    sql = "SELECT c.region FROM Commandes c"
    validated = validate_read_query(sql, allowed_relations=_COLUMNS)
    message = scoped_column_diagnostic(_binder_failure(sql), relations=validated.diagnostic_relations, mounted_columns=_COLUMNS)

    assert "Clients" not in message
    assert "secret_internal_label" not in message
    assert "Available column examples" in message


@pytest.mark.parametrize(
    "sql, candidate",
    [
        ("SELECT c.region FROM Commandes c JOIN Clients cl USING(client_id)", '"cl"."region"'),
        ('SELECT "Order Alias".region FROM Commandes AS "Order Alias" JOIN Clients AS "Client Alias" USING(client_id)', '"Client Alias"."region"'),
        ('SELECT "Order Alias".REGION FROM Commandes AS "Order Alias" JOIN Clients AS "Client Alias" USING(client_id)', '"Client Alias"."region"'),
        ("SELECT c.region FROM Commandes c JOIN Clients cl ON c.client_id=cl.client_id", '"cl"."region"'),
    ],
)
def test_explicitly_joined_visible_column_is_a_candidate(sql: str, candidate: str) -> None:
    message = _diagnostic(sql)

    assert "Visible references in the tables already used by this SQL" in message
    assert candidate in message
    assert "secret_internal_label" not in message


def test_ambiguous_column_shows_both_qualified_choices_without_selecting_one() -> None:
    message = _diagnostic("SELECT devise FROM Commandes c JOIN Clients cl USING(client_id)")

    assert 'Visible qualified references: "c"."devise", "cl"."devise"' in message
    assert "Choose the intended table explicitly" in message
    assert "secret_internal_label" not in message


def test_unqualified_missing_column_lists_only_visible_columns() -> None:
    message = _diagnostic("SELECT offre FROM Commandes")

    assert 'Column "offre" does not exist in "Commandes"' in message
    assert '"Commandes"."commande_id"' in message
    assert "Clients" not in message


@pytest.mark.parametrize(
    "sql",
    [
        "WITH scoped AS (SELECT client_id FROM Clients) SELECT s.region FROM scoped s",
        "SELECT x.region FROM (SELECT client_id FROM Clients) x",
        "SELECT c.region FROM Commandes c WHERE EXISTS (SELECT 1 FROM Clients cl)",
        "SELECT c.region FROM Commandes c UNION ALL SELECT region FROM Clients",
        "SELECT c.region FROM Commandes AS c(x, y, z)",
        "SELECT c.region FROM Commandes c SEMI JOIN Clients cl USING(client_id)",
        "SELECT c.region FROM Commandes c ANTI JOIN Clients cl USING(client_id)",
    ],
)
def test_derived_or_hidden_scope_keeps_original_diagnostic_without_candidates(sql: str) -> None:
    validated = validate_read_query(sql, allowed_relations=_COLUMNS)
    original = _binder_failure(sql)

    assert validated.diagnostic_relations == ()
    assert scoped_column_diagnostic(original, relations=validated.diagnostic_relations, mounted_columns=_COLUMNS) == original


def test_unknown_join_qualifier_keeps_original_diagnostic() -> None:
    sql = "SELECT j.absent FROM (Commandes c JOIN Clients cl USING(client_id)) j"
    validated = validate_read_query(sql, allowed_relations=_COLUMNS)
    original = _binder_failure(sql)

    assert scoped_column_diagnostic(original, relations=validated.diagnostic_relations, mounted_columns=_COLUMNS) == original


def test_later_join_column_is_not_suggested_inside_an_earlier_on_clause() -> None:
    sql = "SELECT c.commande_id FROM Commandes c JOIN Commandes c2 ON c.region=c2.client_id JOIN Clients cl ON c.client_id=cl.client_id"
    validated = validate_read_query(sql, allowed_relations=_COLUMNS)
    original = _binder_failure(sql)

    assert validated.diagnostic_relations == ()
    assert scoped_column_diagnostic(original, relations=validated.diagnostic_relations, mounted_columns=_COLUMNS) == original


def test_missing_mounted_schema_never_triggers_a_lookup_or_partial_guess() -> None:
    sql = "SELECT c.region FROM Commandes c JOIN Clients cl USING(client_id)"
    validated = validate_read_query(sql, allowed_relations=_COLUMNS)
    original = _binder_failure(sql)

    assert scoped_column_diagnostic(original, relations=validated.diagnostic_relations, mounted_columns={"Commandes": _COLUMNS["Commandes"]}) == original


def test_unsupported_binder_error_preserves_the_original_message() -> None:
    validated = validate_read_query("SELECT c.commande_id FROM Commandes c", allowed_relations=_COLUMNS)
    original = "Binder Error: No function matches the given name and argument types"

    assert scoped_column_diagnostic(original, relations=validated.diagnostic_relations, mounted_columns=_COLUMNS) == original


def test_diagnostic_never_opens_a_connection_or_reparses_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    sql = "SELECT c.region FROM Commandes c"
    validated = validate_read_query(sql, allowed_relations=_COLUMNS)
    original = _binder_failure(sql)

    def forbidden_connect(*args: object, **kwargs: object) -> None:
        raise AssertionError("Diagnostics must not open a connection")

    monkeypatch.setattr(duckdb, "connect", forbidden_connect)
    message = scoped_column_diagnostic(original, relations=validated.diagnostic_relations, mounted_columns={"Commandes": _COLUMNS["Commandes"]})

    assert "Available column examples" in message
    assert validated.sql == sql


def test_validation_only_uses_its_existing_parser_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    original_connect = duckdb.connect
    opened = []

    def record_connect(*args: object, **kwargs: object) -> duckdb.DuckDBPyConnection:
        opened.append(1)
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(duckdb, "connect", record_connect)
    validated = validate_read_query("SELECT c.region FROM Commandes c", allowed_relations=_COLUMNS)

    assert len(opened) == 1
    assert validated.diagnostic_relations == (VisibleQueryRelation("Commandes", "c"),)


def test_column_examples_are_bounded_and_quotes_are_sql_escaped() -> None:
    original = 'Binder Error: Table "c" does not have a column named "missing"'
    message = scoped_column_diagnostic(
        original,
        relations=(VisibleQueryRelation("Commandes", "c"),),
        mounted_columns={"Commandes": ['column"quoted', *[f"field_{index}" for index in range(1000)]]},
    )

    assert '"c"."column""quoted"' in message
    assert '"field_6"' in message
    assert '"field_7"' not in message
    assert len(message) <= 4096


def test_long_or_unknown_diagnostic_is_bounded() -> None:
    message = scoped_column_diagnostic("Binder Error: " + "x" * 10000, relations=(), mounted_columns={})

    assert len(message) == 4096
