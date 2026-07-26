"""Rate limiter and universe-filter regressions.

Both cover code that was written but had never been executed. The
limiter in particular is the kind of thing that looks obviously correct
and silently does nothing — if the window bookkeeping is wrong it just
never blocks, and the only symptom is throttling from the server much
later, under load, in a run that's expensive to repeat.
"""
import time
import unittest

from screener import rate_limit, universe


class RateLimiterTest(unittest.TestCase):
    def test_blocks_once_the_window_is_full(self):
        limiter = rate_limit.RateLimiter(max_calls=10, window_seconds=1.0, safety_margin=1.0)
        started = time.monotonic()
        for _ in range(15):
            limiter.acquire()
        elapsed = time.monotonic() - started
        # The first 10 go straight through; the next 5 must wait for the
        # earliest to age out, so this cannot finish inside the window.
        self.assertGreater(elapsed, 0.5)

    def test_does_not_block_below_the_limit(self):
        limiter = rate_limit.RateLimiter(max_calls=50, window_seconds=60.0, safety_margin=1.0)
        started = time.monotonic()
        for _ in range(20):
            limiter.acquire()
        self.assertLess(time.monotonic() - started, 0.5)

    def test_safety_margin_reserves_headroom(self):
        limiter = rate_limit.RateLimiter(max_calls=100, window_seconds=60.0, safety_margin=0.9)
        _, limit = limiter.snapshot()
        self.assertEqual(limit, 90)

    def test_snapshot_reports_usage(self):
        limiter = rate_limit.RateLimiter(max_calls=10, window_seconds=60.0, safety_margin=1.0)
        for _ in range(3):
            limiter.acquire()
        used, limit = limiter.snapshot()
        self.assertEqual(used, 3)
        self.assertEqual(limit, 10)

    def test_documented_quota_is_encoded(self):
        """The published limit is 300 per 60 seconds — not the 600 I'd
        assumed before checking.
        """
        self.assertEqual(rate_limit.MAX_CALLS, 300)
        self.assertEqual(rate_limit.WINDOW_SECONDS, 60.0)


class UniverseFilterTest(unittest.TestCase):
    def _instrument(self, **overrides):
        base = {
            "symbol": "AAA", "status": "OC", "exchange_code": "NYSE",
            "etf_leveraged_flag": "NO", "single_stock_etf": False, "crypto_etf": False,
        }
        base.update(overrides)
        return base

    def test_accepts_a_tradable_major_exchange_listing(self):
        self.assertTrue(universe.is_screenable(self._instrument()))

    def test_rejects_non_tradable_status(self):
        self.assertFalse(universe.is_screenable(self._instrument(status="NT")))

    def test_rejects_otc_venues(self):
        for venue in ("PINL", "PK", "OTCID", "OTCB"):
            self.assertFalse(universe.is_screenable(self._instrument(exchange_code=venue)), venue)

    def test_rejects_derivative_etfs(self):
        """Stage analysis of a leveraged product reads the product's decay,
        not the underlying's trend.
        """
        self.assertFalse(universe.is_screenable(self._instrument(etf_leveraged_flag="YES")))
        self.assertFalse(universe.is_screenable(self._instrument(single_stock_etf=True)))
        self.assertFalse(universe.is_screenable(self._instrument(crypto_etf=True)))

    def test_liquidity_filter_uses_dollar_volume_not_share_volume(self):
        """A $3 stock trading a million shares is not the same market as a
        $300 one trading the same.
        """
        def bars(close, volume):
            return [{"close": close, "volume": volume} for _ in range(12)]

        kept = universe.filter_by_liquidity(
            {"CHEAP": bars(3.0, 1_000_000), "RICH": bars(300.0, 1_000_000)},
            min_dollar_volume=10_000_000, report=False,
        )
        self.assertNotIn("CHEAP", kept)
        self.assertIn("RICH", kept)

    def test_liquidity_filter_tolerates_empty_series(self):
        self.assertEqual(universe.filter_by_liquidity({"X": []}, report=False), {})


if __name__ == "__main__":
    unittest.main()
