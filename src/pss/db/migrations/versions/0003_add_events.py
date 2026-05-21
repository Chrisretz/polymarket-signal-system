"""Add events and event_snapshots tables (Strategi C research).

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("slug", sa.Text(), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("neg_risk", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("raw_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("idx_events_active", "events", ["is_active"], unique=False)
    op.create_index("idx_events_end_date", "events", ["end_date"], unique=False)

    op.create_table(
        "event_snapshots",
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leg_count", sa.Integer(), nullable=False),
        sa.Column("sum_yes_prices", sa.Numeric(8, 5), nullable=False),
        sa.Column("inconsistency_pp", sa.Numeric(8, 5), nullable=False),
        sa.Column("min_leg_liquidity_usd", sa.Numeric(18, 2), nullable=True),
        sa.Column("leg_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id", "snapshot_at"),
    )
    op.execute(
        """
        SELECT create_hypertable(
            'event_snapshots',
            'snapshot_at',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        )
        """,
    )
    op.create_index(
        "idx_event_snapshots_event",
        "event_snapshots",
        ["event_id", sa.text("snapshot_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_event_snapshots_event", table_name="event_snapshots")
    op.drop_table("event_snapshots")
    op.drop_index("idx_events_end_date", table_name="events")
    op.drop_index("idx_events_active", table_name="events")
    op.drop_table("events")
