# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""One structured outcome line per tabular document, shared by CSV and Excel ingestion."""

import logging
from collections.abc import Sequence

logger = logging.getLogger(__name__)


def log_tabular_outcome(document_uid: str, *, tables: Sequence[tuple[int, int]], size_bytes: int, duration_ms: float, **counts: int) -> None:
    """Log what a tabular extraction produced, as counts only.

    `tables` holds one `(rows, columns)` pair per stored table. Names (file, sheet,
    table, column, alias) and paths never appear: they derive from user content.
    `counts` carries bounded extras such as `sheets` or `empty_tables`.
    """
    rows = sum(table_rows for table_rows, _ in tables)
    logger.info(
        "tabular outcome document_uid=%s tables=%s rows=%s size_bytes=%s duration_ms=%.0f",
        document_uid,
        len(tables),
        rows,
        size_bytes,
        duration_ms,
        extra={
            "document_uid": document_uid,
            "tables": len(tables),
            "rows": rows,
            "columns": [table_columns for _, table_columns in tables],
            "size_bytes": size_bytes,
            "duration_ms": round(duration_ms),
            **counts,
        },
    )
