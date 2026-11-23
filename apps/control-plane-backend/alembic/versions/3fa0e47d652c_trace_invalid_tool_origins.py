# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Index invalid tool occurrences in retained model evidence.

Revision ID: 3fa0e47d652c
Revises: c1a4bf6de820
"""

import sqlalchemy as sa
from alembic import op

revision = "3fa0e47d652c"  # pragma: allowlist secret
down_revision = "c1a4bf6de820"  # pragma: allowlist secret
branch_labels = None
depends_on = None

_TABLE = "conversation_trace_invalid_tool"
_TRIGGER = "sync_conversation_trace_invalid_tool"
_INSERT = f"""
    INSERT INTO {_TABLE}
        (capture_id, session_id, fingerprint, history_rank, exchange_id,
         call_order, call_id, observed_through_rank)
"""
_POSTGRES_SELECT = """
    CROSS JOIN LATERAL json_array_elements(
        CASE WHEN json_typeof(turn.model_calls) = 'array' THEN turn.model_calls END
    ) WITH ORDINALITY AS model(value, ordinal)
    CROSS JOIN LATERAL json_array_elements_text(
        CASE WHEN json_typeof(model.value -> 'observed_invalid_tools') = 'array'
             THEN model.value -> 'observed_invalid_tools' END
    ) AS invalid(fingerprint)
    WHERE invalid.fingerprint ~ '^[0-9a-f]{64}$'
"""
_SQLITE_SELECT = """
    CROSS JOIN json_each(turn.model_calls) AS model
    CROSS JOIN json_each(model.value, '$.observed_invalid_tools') AS invalid
    WHERE json_type(model.value, '$.observed_invalid_tools') = 'array'
      AND length(invalid.value) = 64 AND invalid.value NOT GLOB '*[^0-9a-f]*'
"""


def _populate_postgres(*, backfill: bool) -> str:
    turns = "conversation_trace_turn AS turn" if backfill else "(SELECT NEW.*) AS turn"
    return f"""
        {_INSERT}
        SELECT DISTINCT turn.capture_id, turn.session_id, invalid.fingerprint,
            turn.history_rank, turn.exchange_id, model.ordinal - 1,
            model.value ->> 'call_id',
            CAST(model.value ->> 'observed_through_rank' AS INTEGER)
        FROM {turns}
        {_POSTGRES_SELECT}
    """


def _populate_sqlite(*, backfill: bool) -> str:
    turns = (
        "conversation_trace_turn AS turn"
        if backfill
        else """(SELECT NEW.capture_id AS capture_id, NEW.session_id AS session_id,
                        NEW.history_rank AS history_rank, NEW.exchange_id AS exchange_id,
                        NEW.model_calls AS model_calls) AS turn"""
    )
    return f"""
        {_INSERT}
        SELECT DISTINCT turn.capture_id, turn.session_id, invalid.value,
            turn.history_rank, turn.exchange_id, model.key,
            json_extract(model.value, '$.call_id'),
            json_extract(model.value, '$.observed_through_rank')
        FROM {turns}
        {_SQLITE_SELECT}
    """


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column(
            "id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True
        ),
        sa.Column(
            "capture_id",
            sa.String(36),
            sa.ForeignKey("conversation_trace_turn.capture_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(255), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("history_rank", sa.Integer(), nullable=False),
        sa.Column("exchange_id", sa.String(255), nullable=False),
        sa.Column("call_order", sa.Integer(), nullable=False),
        sa.Column("call_id", sa.String(255), nullable=False),
        sa.Column("observed_through_rank", sa.Integer()),
    )
    op.create_index(f"ix_{_TABLE}_capture_id", _TABLE, ["capture_id"])
    op.create_index(
        f"ix_{_TABLE}_first",
        _TABLE,
        ["session_id", "fingerprint", "history_rank", "exchange_id", "call_order"],
        unique=True,
    )
    remove_prior = f"DELETE FROM {_TABLE} WHERE capture_id = NEW.capture_id"
    # Triggers maintain the projection during mixed Control Plane rollouts.
    if op.get_context().dialect.name == "postgresql":
        op.execute(f"""
            CREATE FUNCTION {_TRIGGER}() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF TG_OP = 'UPDATE' THEN
                    {remove_prior};
                END IF;
                {_populate_postgres(backfill=False)};
                RETURN NULL;
            END;
            $$
        """)
        op.execute(f"""
            CREATE TRIGGER {_TRIGGER}
            AFTER INSERT OR UPDATE OF model_calls ON conversation_trace_turn
            FOR EACH ROW EXECUTE FUNCTION {_TRIGGER}()
        """)
        op.execute(_populate_postgres(backfill=True))
    else:
        # Install updates first so a row projected during rollout stays current.
        for operation, before in (
            ("UPDATE OF model_calls", remove_prior + ";"),
            ("INSERT", ""),
        ):
            op.execute(f"""
                CREATE TRIGGER {_TRIGGER}_{operation.split()[0].lower()}
                AFTER {operation} ON conversation_trace_turn
                BEGIN
                    {before}
                    {_populate_sqlite(backfill=False)};
                END
            """)
        # Local SQLite connections may leave foreign-key enforcement disabled.
        op.execute(f"""
            CREATE TRIGGER {_TRIGGER}_delete
            AFTER DELETE ON conversation_trace_turn
            BEGIN
                DELETE FROM {_TABLE} WHERE capture_id = OLD.capture_id;
            END
        """)
        op.execute(
            _populate_sqlite(backfill=True)
            + "ON CONFLICT (session_id, fingerprint, history_rank, exchange_id, call_order)"
            + " DO NOTHING"
        )


def downgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.execute(f"DROP TRIGGER {_TRIGGER} ON conversation_trace_turn")
        op.execute(f"DROP FUNCTION {_TRIGGER}()")
    else:
        op.execute(f"DROP TRIGGER {_TRIGGER}_delete")
        op.execute(f"DROP TRIGGER {_TRIGGER}_insert")
        op.execute(f"DROP TRIGGER {_TRIGGER}_update")
    op.drop_table(_TABLE)
