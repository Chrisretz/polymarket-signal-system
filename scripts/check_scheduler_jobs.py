"""Vis planlagte scheduler-jobs uden at starte den langtkørende proces."""

from __future__ import annotations

from pss.logging_config import configure_logging
from pss.scheduler import setup_scheduler


def main() -> None:
    configure_logging()
    scheduler = setup_scheduler(run_immediately=False)

    print("Registrerede jobs (UTC):\n")
    for job in scheduler.get_jobs():
        print(f"  {job.id}")
        print(f"    navn: {job.name}")
        print(f"    trigger: {job.trigger}")
        print(f"    næste kørsel (efter start): {job.next_run_time}")
        print()

    print("check_scheduler_jobs: ok")


if __name__ == "__main__":
    main()
