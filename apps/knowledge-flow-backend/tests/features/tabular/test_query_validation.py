from __future__ import annotations

import pytest

from knowledge_flow_backend.features.tabular.utils import validate_read_query


def test_validate_read_query_allows_authorized_cte_references():
    query = "WITH scoped AS (SELECT * FROM d_sales) SELECT * FROM scoped"

    validated = validate_read_query(query, allowed_relations={"d_sales"})

    assert validated.sql == query
    # The CTE name is not a dataset and must never reach the mount set.
    assert validated.referenced_relations == frozenset({"d_sales"})


def test_validate_read_query_collects_natural_join_relations():
    query = "SELECT * FROM d_sales NATURAL JOIN d_targets"

    validated = validate_read_query(query, allowed_relations={"d_sales", "d_targets"})

    assert validated.sql == query
    assert validated.referenced_relations == frozenset({"d_sales", "d_targets"})


def test_validate_read_query_reports_only_the_referenced_subset_of_allowed_relations():
    """The mount set must follow the query, not the whole authorized selection."""

    validated = validate_read_query(
        "SELECT city FROM d_sales",
        allowed_relations={"d_sales", "d_targets", "d_stock"},
    )

    assert validated.referenced_relations == frozenset({"d_sales"})


def test_validate_read_query_reports_no_relation_for_a_scalar_only_query():
    validated = validate_read_query("SELECT 1", allowed_relations={"d_sales"})

    assert validated.referenced_relations == frozenset()


def test_validate_read_query_rejects_table_functions_hidden_behind_natural_join():
    with pytest.raises(ValueError, match=r"unauthorized datasets: read_parquet\(\)"):
        validate_read_query(
            "SELECT * FROM d_sales NATURAL JOIN read_parquet('/tmp/forbidden.parquet')",
            allowed_relations={"d_sales"},
        )


def test_validate_read_query_rejects_scalar_subqueries_on_unauthorized_datasets():
    with pytest.raises(ValueError, match=r"unauthorized datasets: d_targets"):
        validate_read_query(
            "SELECT (SELECT COUNT(*) FROM d_targets) AS total_rows FROM d_sales",
            allowed_relations={"d_sales"},
        )


def test_validate_read_query_rejects_schema_qualified_tables_even_when_base_name_matches():
    with pytest.raises(ValueError, match=r"unauthorized datasets: pg_catalog\.pg_tables"):
        validate_read_query(
            "SELECT * FROM pg_catalog.pg_tables",
            allowed_relations={"pg_tables"},
        )


def test_validate_read_query_keeps_the_full_sql_line_in_parser_errors():
    query = 'SELCT DISTINCT "Véhicule" FROM d_9600f46d555f_parc_automobile_t1 WHERE "Véhicule" IS NOT NULL ORDER BY "Véhicule"'

    with pytest.raises(ValueError) as error:
        validate_read_query(
            query,
            allowed_relations={"d_9600f46d555f_parc_automobile_t1"},
        )

    message = str(error.value)
    assert 'syntax error at or near "SELCT"' in message
    assert f"LINE 1: {query}" in message
    assert "..." not in message
