"""Event-hierarki under tracked groups.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tracked_group_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("event_title", sa.Text(), nullable=False),
        sa.Column("event_slug", sa.Text(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["group_id"], ["tracked_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "group_id",
            "event_id",
            name="uq_tracked_group_events_group_event_id",
        ),
        sa.UniqueConstraint(
            "group_id",
            "event_slug",
            name="uq_tracked_group_events_group_event_slug",
        ),
    )
    op.create_index(
        "idx_tracked_group_events_group",
        "tracked_group_events",
        ["group_id"],
        unique=False,
    )

    op.add_column(
        "tracked_group_markets",
        sa.Column("group_event_id", sa.BigInteger(), nullable=True),
    )

    conn = op.get_bind()
    groups = conn.execute(sa.text("SELECT id FROM tracked_groups")).fetchall()
    for row in groups:
        gid = row[0]
        legacy_event_id = f"legacy-{gid}"
        legacy_slug = f"legacy-import-{gid}"
        insert = conn.execute(
            sa.text(
                """
                INSERT INTO tracked_group_events
                    (group_id, event_id, event_title, event_slug, added_at)
                VALUES
                    (:gid, :eid, 'Imported markets (legacy)', :slug, now())
                RETURNING id
                """,
            ),
            {"gid": gid, "eid": legacy_event_id, "slug": legacy_slug},
        )
        group_event_pk = insert.scalar_one()
        conn.execute(
            sa.text(
                """
                UPDATE tracked_group_markets
                SET group_event_id = :geid
                WHERE group_id = :gid
                """,
            ),
            {"geid": group_event_pk, "gid": gid},
        )

    op.create_foreign_key(
        "fk_tracked_group_markets_group_event",
        "tracked_group_markets",
        "tracked_group_events",
        ["group_event_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_tracked_group_markets_group_event",
        "tracked_group_markets",
        ["group_event_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_tracked_group_markets_group_event", table_name="tracked_group_markets")
    op.drop_constraint(
        "fk_tracked_group_markets_group_event",
        "tracked_group_markets",
        type_="foreignkey",
    )
    op.drop_column("tracked_group_markets", "group_event_id")
    op.drop_index("idx_tracked_group_events_group", table_name="tracked_group_events")
    op.drop_table("tracked_group_events")
