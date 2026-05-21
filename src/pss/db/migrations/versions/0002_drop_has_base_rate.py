"""Drop has_base_rate from markets (Strategi A cleanup).

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("idx_markets_has_base_rate", table_name="markets", if_exists=True)
    op.drop_column("markets", "has_base_rate")


def downgrade() -> None:
    op.add_column(
        "markets",
        sa.Column(
            "has_base_rate",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "idx_markets_has_base_rate",
        "markets",
        ["has_base_rate"],
        unique=False,
    )
