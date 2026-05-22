"""Outcome-side per tracked market + drop duplicate market unique constraint.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tracked_group_markets",
        sa.Column("outcome_side", sa.Text(), server_default=sa.text("'yes'"), nullable=False),
    )
    op.drop_constraint("uq_tracked_group_markets_group_market", "tracked_group_markets", type_="unique")
    op.create_unique_constraint(
        "uq_tracked_group_markets_group_market_outcome",
        "tracked_group_markets",
        ["group_id", "market_id", "outcome_side"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_tracked_group_markets_group_market_outcome",
        "tracked_group_markets",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_tracked_group_markets_group_market",
        "tracked_group_markets",
        ["group_id", "market_id"],
    )
    op.drop_column("tracked_group_markets", "outcome_side")
