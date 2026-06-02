from __future__ import annotations

import pytest

from knowledge_flow_backend.features.tabular.utils import validate_read_query


def test_validate_read_query_allows_authorized_cte_references():
    query = "WITH scoped AS (SELECT * FROM d_sales) SELECT * FROM scoped"

    normalized = validate_read_query(query, allowed_relations={"d_sales"})

    assert normalized == query


def test_validate_read_query_collects_natural_join_relations():
    query = "SELECT * FROM d_sales NATURAL JOIN d_targets"

    normalized = validate_read_query(query, allowed_relations={"d_sales", "d_targets"})

    assert normalized == query


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
