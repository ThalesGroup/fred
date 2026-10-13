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

"""Announcement history by exposure, and patch notes announced as packages.

Activation events become one line per exposure. The enabled patch notes become
the first package, readable and pending for nobody. Downgrading rebuilds the
events from the lines and loses the packages.

Revision ID: a6c1d94e27b3
Revises: e5ff6d80cc9f
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a6c1d94e27b3"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "e5ff6d80cc9f"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EVENTS = "platform_announcement_activation_event"
_EXPOSURES = "platform_announcement_exposure"
# Announcements follow one another whatever note they name: one pairing key.
_ANNOUNCED = object()

_events = sa.table(
    _EVENTS,
    sa.column("id", sa.String),
    sa.column("announcement_id", sa.String),
    sa.column("kind", sa.String),
    sa.column("label", sa.JSON),
    sa.column("action", sa.String),
    sa.column("severity", sa.String),
    sa.column("actor_uid", sa.String),
    sa.column("occurred_at", sa.DateTime(timezone=True)),
)
_exposures = sa.table(
    _EXPOSURES,
    sa.column("id", sa.String),
    sa.column("kind", sa.String),
    sa.column("announcement_id", sa.String),
    sa.column("label", sa.JSON),
    sa.column("severity", sa.String),
    sa.column("actor_uid", sa.String),
    sa.column("activated_at", sa.DateTime(timezone=True)),
    sa.column("deactivated_at", sa.DateTime(timezone=True)),
    sa.column("note_count", sa.Integer),
    sa.column("package", sa.JSON(none_as_null=True)),
    sa.column("opens_dialog", sa.Boolean),
)
_announcements = sa.table(
    "platform_announcement",
    sa.column("id", sa.String),
    sa.column("kind", sa.String),
    sa.column("title", sa.JSON),
    sa.column("description_long", sa.JSON),
    sa.column("enabled", sa.Boolean),
    sa.column("position", sa.Integer),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def _line(event: Any) -> dict[str, Any]:
    return {
        "id": event.id,
        "kind": event.kind,
        "announcement_id": event.announcement_id,
        "label": event.label,
        "severity": event.severity,
        "actor_uid": event.actor_uid,
        "activated_at": event.occurred_at,
        "deactivated_at": None,
        "note_count": None,
        "package": None,
        "opens_dialog": True,
    }


def _lines_from_events(events: Sequence[Any]) -> list[dict[str, Any]]:
    """Pair each start with the end that follows it for the same subject."""
    lines: list[dict[str, Any]] = []
    open_lines: dict[Any, dict[str, Any]] = {}
    for event in events:
        announcing = event.action in ("announced", "unannounced")
        key = _ANNOUNCED if announcing else event.announcement_id
        previous = open_lines.pop(key, None)
        if previous is not None:
            previous["deactivated_at"] = event.occurred_at
        if event.action in ("activated", "announced"):
            open_lines[key] = _line(event)
            lines.append(open_lines[key])
    return lines


def _first_package(connection: sa.Connection, now: datetime) -> dict[str, Any] | None:
    """The enabled patch notes, frozen as users can read them today."""
    notes = connection.execute(
        sa.select(
            _announcements.c.id,
            _announcements.c.title,
            _announcements.c.description_long,
        )
        .where(_announcements.c.kind == "patch_note", _announcements.c.enabled)
        .order_by(
            _announcements.c.position.asc(),
            _announcements.c.created_at.desc(),
            _announcements.c.id.desc(),
        )
    ).all()
    if not notes:
        return None
    return {
        "id": str(uuid.uuid4()),
        "kind": "patch_note",
        "announcement_id": notes[0].id,
        "label": notes[0].title,
        "severity": None,
        "actor_uid": None,
        "activated_at": now,
        "deactivated_at": None,
        "note_count": len(notes),
        "package": [
            {"id": n.id, "title": n.title, "description_long": n.description_long}
            for n in notes
        ],
        # Users already had this content: readable, pending for nobody.
        "opens_dialog": False,
    }


def upgrade() -> None:
    op.create_table(
        _EXPOSURES,
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "announcement_id",
            sa.String(),
            nullable=False,
            comment="The banner; for a package, its first patch note.",
        ),
        sa.Column(
            "label",
            sa.JSON(),
            nullable=False,
            comment="Locale → title when the exposure started.",
        ),
        sa.Column(
            "severity",
            sa.String(length=16),
            nullable=True,
            comment="Banner severity when the exposure started; null for patch notes.",
        ),
        sa.Column("actor_uid", sa.String(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "deactivated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Null while users still see it.",
        ),
        sa.Column(
            "note_count",
            sa.Integer(),
            nullable=True,
            comment="Patch notes in the package; null when the row keeps none.",
        ),
        sa.Column(
            "package",
            sa.JSON(none_as_null=True),
            nullable=True,
            comment="The announced patch notes, frozen: "
            "[{id, title, description_long}].",
        ),
        sa.Column(
            "opens_dialog",
            sa.Boolean(),
            server_default="true",
            nullable=False,
            comment="False only for the package the upgrade created: readable, "
            "pending for nobody.",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_platform_announcement_exposure_activated_at"),
        _EXPOSURES,
        ["activated_at"],
        unique=False,
    )

    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    events = connection.execute(
        sa.select(_events).order_by(_events.c.occurred_at.asc(), _events.c.id.asc())
    ).all()
    lines = _lines_from_events(events)
    for line in lines:
        # No earlier patch-note line stays in effect: none kept its content.
        if line["kind"] == "patch_note" and line["deactivated_at"] is None:
            line["deactivated_at"] = now
    package = _first_package(connection, now)
    if package is not None:
        lines.append(package)
    if lines:
        op.bulk_insert(_exposures, lines)

    with op.batch_alter_table("platform_announcement_seen") as batch:
        batch.alter_column(
            "announcement_event_id",
            new_column_name="announcement_id",
            existing_type=sa.String(),
            existing_nullable=False,
        )
    op.drop_index(
        op.f("ix_platform_announcement_activation_event_occurred_at"),
        table_name=_EVENTS,
    )
    op.drop_table(_EVENTS)


def _event(line: Any, action: str, occurred_at: datetime, event_id: str) -> dict:
    return {
        "id": event_id,
        "announcement_id": line.announcement_id,
        "kind": line.kind,
        "label": line.label,
        "action": action,
        "severity": line.severity,
        # Who ended an exposure was not kept.
        "actor_uid": line.actor_uid if event_id == line.id else None,
        "occurred_at": occurred_at,
    }


def downgrade() -> None:
    op.create_table(
        _EVENTS,
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("announcement_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "label",
            sa.JSON(),
            nullable=False,
            comment="Locale → title at event time.",
        ),
        sa.Column(
            "action",
            sa.String(length=16),
            nullable=False,
            comment="activated | deactivated | announced | unannounced",
        ),
        sa.Column(
            "severity",
            sa.String(length=16),
            nullable=True,
            comment="Banner severity at event time; null for a patch note.",
        ),
        sa.Column("actor_uid", sa.String(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_platform_announcement_activation_event_occurred_at"),
        _EVENTS,
        ["occurred_at"],
        unique=False,
    )

    connection = op.get_bind()
    lines = connection.execute(
        sa.select(_exposures).order_by(
            _exposures.c.activated_at.asc(), _exposures.c.id.asc()
        )
    ).all()
    events: list[dict] = []
    last_announced = None
    for line in lines:
        if line.note_count is None:
            events.append(_event(line, "activated", line.activated_at, line.id))
            if line.deactivated_at is not None:
                events.append(
                    _event(line, "deactivated", line.deactivated_at, str(uuid.uuid4()))
                )
        # The upgrade's own package was never announced: it would open a dialog.
        elif line.opens_dialog:
            events.append(_event(line, "announced", line.activated_at, line.id))
            last_announced = line
    if last_announced is not None and last_announced.deactivated_at is not None:
        events.append(
            _event(
                last_announced,
                "unannounced",
                last_announced.deactivated_at,
                str(uuid.uuid4()),
            )
        )
    if events:
        op.bulk_insert(_events, events)

    with op.batch_alter_table("platform_announcement_seen") as batch:
        batch.alter_column(
            "announcement_id",
            new_column_name="announcement_event_id",
            existing_type=sa.String(),
            existing_nullable=False,
        )
    op.drop_index(
        op.f("ix_platform_announcement_exposure_activated_at"),
        table_name=_EXPOSURES,
    )
    op.drop_table(_EXPOSURES)
