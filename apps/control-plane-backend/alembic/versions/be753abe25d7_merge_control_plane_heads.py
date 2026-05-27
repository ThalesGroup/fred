"""merge control-plane migration heads

Revision ID: be753abe25d7
Revises: c789f5ab40fe, f1a2b3c4d5e6
Create Date: 2026-04-25 03:43:10.983677

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "be753abe25d7"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "c789f5ab40fe",  # pragma: allowlist secret
    "f1a2b3c4d5e6",  # pragma: allowlist secret
)  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Record a merge so Alembic has a single upgrade target.

    Why:
        The control-plane schema history temporarily had two Alembic heads:
        one for `users` and one for `agent_instance` / `session_metadata`.
        This merge makes the deployment path explicit and restores a single
        upgrade target.

    How to use:
        Run `alembic upgrade head` from either side of the split history.
        Alembic will apply whichever branch is missing, then mark this merge
        revision as the unique head.
    """
    pass


def downgrade() -> None:
    """Re-open both branches by removing the merge marker only.

    Why:
        A merge revision has no schema change of its own; it only joins two
        compatible histories into one head.

    How to use:
        Downgrading from this revision removes the merge point and leaves the
        database on the two predecessor revisions.
    """
    pass
