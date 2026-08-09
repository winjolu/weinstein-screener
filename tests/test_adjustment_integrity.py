"""The dividend adjustment can be broken without looking broken.

Sharadar's fund table carries a `closeadj` that has been divided toward
zero for some distribution-heavy ETFs. FTHI's adjusted close a year
before 2026-08-03 is $0.0003 against a real price of $23.00, so a
twelve-month return computed from it comes back as 7,946,566%.

Nothing about that fails loudly. It ranked third on a live screen and
looked like the best momentum in the market, which is exactly how the
Webull split corruption presented before it was found.

The check that separates good series from bad is the *drift* in
closeadj/close over the window. A healthy series moves a few percent as
dividends accrue. A broken one moves by four or five orders of
magnitude.

Skips when the local Sharadar cache is absent, in the same way as the
cross-vendor agreement test — this guards data, and there is no data to
guard on a fresh clone.
"""
import os
import sqlite3
import unittest

CACHE = os.environ.get("SHARADAR_DB",
                       os.path.expanduser("~/market-data/sharadar.db"))
MAX_DRIFT = 1.5      # a year of dividends never moves the ratio this far


def _drift(conn, table, ticker, asof="2025-08-06"):
    then = conn.execute(
        f"SELECT close, closeadj FROM {table} WHERE ticker=? AND date<=? "
        f"ORDER BY date DESC LIMIT 1", (ticker, asof)).fetchone()
    now = conn.execute(
        f"SELECT close, closeadj FROM {table} WHERE ticker=? "
        f"ORDER BY date DESC LIMIT 1", (ticker,)).fetchone()
    if not then or not now or not then[0] or not now[0]:
        return None
    a, b = then[1] / then[0], now[1] / now[0]
    return (b / a) if a else None


@unittest.skipUnless(os.path.exists(CACHE), "no local Sharadar cache")
class AdjustmentDriftTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(CACHE)
        self.addCleanup(self.conn.close)

    def test_the_broad_index_funds_are_sane(self):
        for t in ("SPY", "QQQ", "DIA", "EWJ", "VTWO"):
            d = _drift(self.conn, "fundprices", t)
            self.assertIsNotNone(d, f"{t} missing")
            self.assertLess(abs(d - 1.0), 0.5, f"{t} adjustment drifted {d:.1f}x")

    def test_the_known_broken_funds_are_still_detected(self):
        # Named rather than described. If Sharadar repairs these the test
        # fails, which is the correct outcome — it means the gate can be
        # loosened, and that decision should be made deliberately.
        for t in ("FTHI", "FTSL", "FTSM"):
            d = _drift(self.conn, "fundprices", t)
            self.assertIsNotNone(d, f"{t} missing")
            self.assertGreater(d, 1000.0,
                               f"{t} drift {d} — was broken, verify before trusting")

    def test_ordinary_stocks_are_not_affected(self):
        for t in ("AAPL", "NVDA", "DELL"):
            d = _drift(self.conn, "prices", t)
            self.assertIsNotNone(d, f"{t} missing")
            self.assertLess(abs(d - 1.0), 0.5, f"{t} adjustment drifted {d:.1f}x")

    def test_the_gate_threshold_actually_separates_the_two_groups(self):
        # A threshold that lets a known-bad series through is worse than
        # no threshold, because it reads as verification.
        good = [_drift(self.conn, "fundprices", t) for t in ("SPY", "QQQ", "DIA")]
        bad = [_drift(self.conn, "fundprices", t) for t in ("FTHI", "FTSL", "FTSM")]
        self.assertTrue(all(g is not None and g < MAX_DRIFT for g in good))
        self.assertTrue(all(b is not None and b > MAX_DRIFT for b in bad))
