"""Deploy database schema via Alembic (Uge 1, Dag 3)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    alembic_cfg = Config(str(ROOT / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")
    print("Database schema deployed (alembic upgrade head).")


if __name__ == "__main__":
    main()
