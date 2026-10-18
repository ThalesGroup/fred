# SPDX-License-Identifier: Apache-2.0
from fred_core.sql.accent_folding import FOLDED_LETTERS, fold_accents
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    bindparam,
    create_engine,
    select,
)


def test_sqlite_folds_columns_and_bound_values_without_parser_overflow():
    # Exercise the complete table on real SQLite, including builds with a fixed
    # parser stack. Compiling SQL alone cannot detect the original overflow.
    cases = [
        ("".join(FOLDED_LETTERS), "".join(FOLDED_LETTERS.values())),
        ("L'ÉTÉ %_ ' OR 1=1 --", "l'ete %_ ' or 1=1 --"),
        ("ŁØЖΩ œæß", "ŁØЖΩ œæß"),
        ("", ""),
        (None, None),
    ]
    engine = create_engine("sqlite://")
    metadata = MetaData()
    rows = Table(
        "fold_samples",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("value", String),
    )
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(
                rows.insert(),
                [{"id": i, "value": value} for i, (value, _) in enumerate(cases)],
            )
            statement = select(
                fold_accents(rows.c.value), fold_accents(bindparam("needle"))
            ).where(rows.c.id == bindparam("row_id"))
            for i, (value, expected) in enumerate(cases):
                assert connection.execute(
                    statement, {"needle": value, "row_id": i}
                ).one() == (expected, expected)
    finally:
        engine.dispose()
