"""Tracked Market Groups — manuelt kurateret overvågning.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tracked_groups",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_tracked_groups_status", "tracked_groups", ["status"], unique=False)

    op.create_table(
        "tracked_group_markets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("market_id", sa.BigInteger(), nullable=False),
        sa.Column("role_label", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["group_id"], ["tracked_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "market_id", name="uq_tracked_group_markets_group_market"),
        sa.UniqueConstraint("group_id", "role_label", name="uq_tracked_group_markets_group_role"),
    )
    op.create_index(
        "idx_tracked_group_markets_group",
        "tracked_group_markets",
        ["group_id"],
        unique=False,
    )
    op.create_index(
        "idx_tracked_group_markets_market",
        "tracked_group_markets",
        ["market_id"],
        unique=False,
    )

    op.create_table(
        "tracked_group_relations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("relation_type", sa.Text(), nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["group_id"], ["tracked_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_tracked_group_relations_group",
        "tracked_group_relations",
        ["group_id"],
        unique=False,
    )

    op.create_table(
        "tracked_group_snapshots",
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculated_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["tracked_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("group_id", "snapshot_at"),
    )
    op.execute(
        """
        SELECT create_hypertable(
            'tracked_group_snapshots',
            'snapshot_at',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        )
        """,
    )
    op.create_index(
        "idx_tracked_group_snapshots_group",
        "tracked_group_snapshots",
        ["group_id", sa.text("snapshot_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_tracked_group_snapshots_group", table_name="tracked_group_snapshots")
    op.drop_table("tracked_group_snapshots")
    op.drop_index("idx_tracked_group_relations_group", table_name="tracked_group_relations")
    op.drop_table("tracked_group_relations")
    op.drop_index("idx_tracked_group_markets_market", table_name="tracked_group_markets")
    op.drop_index("idx_tracked_group_markets_group", table_name="tracked_group_markets")
    op.drop_table("tracked_group_markets")
    op.drop_index("idx_tracked_groups_status", table_name="tracked_groups")
    op.drop_table("tracked_groups")
