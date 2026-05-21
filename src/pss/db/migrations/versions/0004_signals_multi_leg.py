"""Add multi-leg arbitrage fields to signals (Strategi C).

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("event_id", sa.Text(), nullable=True))
    op.add_column(
        "signals",
        sa.Column("legs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("signals", sa.Column("sum_yes_prices", sa.Numeric(8, 5), nullable=True))
    op.add_column("signals", sa.Column("inconsistency_pp", sa.Numeric(8, 5), nullable=True))
    op.add_column("signals", sa.Column("net_edge_pp", sa.Numeric(8, 5), nullable=True))
    op.add_column(
        "signals",
        sa.Column("min_leg_liquidity_usd", sa.Numeric(18, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("signals", "min_leg_liquidity_usd")
    op.drop_column("signals", "net_edge_pp")
    op.drop_column("signals", "inconsistency_pp")
    op.drop_column("signals", "sum_yes_prices")
    op.drop_column("signals", "legs")
    op.drop_column("signals", "event_id")
