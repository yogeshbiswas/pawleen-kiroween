"""Shared pytest fixtures. Kept minimal; later tasks add fakes here."""
import os
import sys

# Make `import app` work no matter where pytest is started from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone


class FakeClock:
    """Mutable clock for day rollover and lockout tests. Call it to get `now`."""

    def __init__(self, now=None):
        self.now = now or datetime(2025, 10, 30, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)
