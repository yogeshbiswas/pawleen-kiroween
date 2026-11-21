"""Shared pytest fixtures. Kept minimal; later tasks add fakes here."""
import os
import sys

# Make `import app` work no matter where pytest is started from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
