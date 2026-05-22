"""Event-level research pipeline for Strategi C (cross-market consistency).

Modules:
    discovery     — find neg_risk events with 3+ legs via Gamma API
    snapshot      — aggregate market snapshots into event_snapshots
    inconsistency — scan for interesting inconsistencies and alert
"""

from pss.events.discovery import discover_events
from pss.events.snapshot import snapshot_events

__all__ = [
    "discover_events",
    "snapshot_events",
]
