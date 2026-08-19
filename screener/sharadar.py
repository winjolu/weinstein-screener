"""Re-exported from the shared package; implemented in market_core.sharadar.

Rebinds the module rather than re-exporting its names. A star import
copies each name into a fresh namespace, so anything patching
screener.sharadar in a test would leave real callers bound to the
original — the failure that surfaced as an unexplained HTTP 403.
"""
import sys

from market_core import sharadar as _shared

sys.modules[__name__] = _shared
