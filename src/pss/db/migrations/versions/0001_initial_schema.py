"""Initial schema: markets, snapshots, signals, positions, m.m.

Revision ID: 0001
Revises:
Create Date: 2026-05-16

"""

from typing import Sequence, Union

from alembic import op

from pss.db.models import Base

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    op.execute(
        """
        SELECT create_hypertable(
            'market_snapshots',
            'snapshot_at',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        )
        """,
    )
    op.execute(
        """
        SELECT create_hypertable(
            'orderbook_depth',
            'snapshot_at',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        )
        """,
    )


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
