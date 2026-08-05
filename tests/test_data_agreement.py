"""Two vendors, independently sourced, checked against each other.

Every result in this project rests on price data being right, and for
most of its life there was no way to know whether it was. Webull was the
only source, so a defect in it was indistinguishable from the truth.

It was not right. 621 Webull tickers carry at least one impossible weekly
move, and GE's series contains an 87% single-week collapse that never
happened — the 2021 reverse split applied to already-adjusted history. In
the derivation window, *every* trade losing more than 60% sat on a ticker
with corrupt data. The R25 stop-ceiling batch was motivated by worst
cases of -70%, -85% and -83% that were largely artifacts.

Sharadar now provides an independent second opinion. Where both sources
have a ticker they should agree closely, and where they do not, the
disagreement is worth knowing about rather than averaging over.

**This is a detector for new divergence, not a re-litigation of the known
corruption.** Roughly 5% of Webull tickers are already known bad, so the
assertions are on the *bulk* of the sample rather than on every name.

Skips cleanly when either cache is absent, which is the normal state on a
fresh clone — both are large, local, and gitignored.
"""
import os
import pickle
import statistics
import unittest

SHARADAR_CACHE = "/private/tmp/claude-501/sharadar/weekly_sharadar.pkl"

# Webull's known-bad share is about 5% of tickers. A sample where more
# than 15% disagree means something new has broken, not that we have
# rediscovered the split bug.
MAX_DISAGREEING_SHARE = 0.15
CLOSE_ENOUGH_PCT = 1.0
SAMPLE_SIZE = 400


def _load_caches():
    try:
        from screener import bar_cache
    except Exception:
        return None, None
    if not os.path.exists(SHARADAR_CACHE):
        return None, None
    try:
        webull = bar_cache.load()
    except Exception:
        return None, None
    if not webull:
        return None, None
    with open(SHARADAR_CACHE, "rb") as fh:
        sharadar = pickle.load(fh)
    return webull, sharadar


class VendorAgreementTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.webull, cls.sharadar = _load_caches()
        if not cls.webull or not cls.sharadar:
            raise unittest.SkipTest(
                "both bar caches required; they are large, local and gitignored")
        cls.shared = sorted(set(cls.webull) & set(cls.sharadar))[:SAMPLE_SIZE]

    def _median_diff(self, ticker):
        """Median % difference on weeks both sources cover, or None."""
        a = {b["time"][:10]: b["close"] for b in self.webull.get(ticker, [])
             if b.get("close")}
        b = {x["time"][:10]: x["close"] for x in self.sharadar.get(ticker, [])
             if x.get("close")}
        both = [(a[d], b[d]) for d in a.keys() & b.keys() if a[d] and b[d]]
        if len(both) < 30:
            return None
        return statistics.median(abs(w - s) / s * 100 for w, s in both)

    def test_the_caches_overlap_enough_to_compare(self):
        self.assertGreater(len(self.shared), 50,
                           "too few shared tickers for the check to mean anything")

    def test_most_tickers_agree_closely(self):
        diffs = [(t, d) for t in self.shared if (d := self._median_diff(t)) is not None]
        self.assertGreater(len(diffs), 50)
        disagreeing = [(t, d) for t, d in diffs if d > CLOSE_ENOUGH_PCT]
        share = len(disagreeing) / len(diffs)
        worst = sorted(disagreeing, key=lambda x: -x[1])[:5]
        self.assertLessEqual(
            share, MAX_DISAGREEING_SHARE,
            f"{share:.0%} of {len(diffs)} tickers disagree by more than "
            f"{CLOSE_ENOUGH_PCT}%. Worst: {worst}. Known bad is ~5%; more than "
            f"{MAX_DISAGREEING_SHARE:.0%} means something new has broken.")

    def test_the_typical_ticker_agrees_very_closely(self):
        # The median across tickers should be near zero even though the
        # tail is known to be bad. If the *middle* of the distribution
        # moves, the problem is systemic rather than per-ticker.
        diffs = [d for t in self.shared if (d := self._median_diff(t)) is not None]
        self.assertLess(statistics.median(diffs), 0.5)

    def test_the_index_agrees(self):
        # SPY drives the market-stage condition and M9's regime gate. If
        # the two sources disagree here, every regime decision is suspect.
        diff = self._median_diff("SPY")
        if diff is None:
            self.skipTest("SPY not in both caches")
        self.assertLess(diff, 0.5)

    def test_a_known_corrupt_ticker_is_still_detected(self):
        # GE is the worked example: Webull applies the 2021 reverse split
        # to history that was already adjusted, so pre-split prices are 8x
        # too high. If this ever stops being detected, the detector has
        # broken rather than the data having been fixed.
        diff = self._median_diff("GE")
        if diff is None:
            self.skipTest("GE not in both caches")
        self.assertGreater(diff, 10.0,
                           "GE's known split corruption is no longer detected")
