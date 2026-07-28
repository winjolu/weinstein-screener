"""Data-layer regressions.

The partial-week case is here because it was the bug that invalidated
this project's only "actionable" signal to date: a still-forming weekly
bar carries a fraction of a full week's volume, which read as healthy
pullback contraction (0.81x) when the completed week was actually
volume expansion (1.44x). Nothing looked wrong in the output.

The batch unpacker is here because it is new, has a silent failure mode
(a symbol that quietly vanishes from a batch of 20 rather than raising),
and had never been exercised when these tests were written.
"""
import datetime
import unittest

from screener import data_fetch


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _raw(symbol, dates):
    """Mimics the API's own shape: newest bar first, numbers as strings."""
    return {
        "symbol": symbol,
        "result": [
            {"time": f"{d}T04:00:00.000+0000", "open": "1", "high": "2",
             "low": "0.5", "close": "1.5", "volume": "1000"}
            for d in reversed(dates)
        ],
    }


class PartialWeekTest(unittest.TestCase):
    def test_current_week_on_a_weekday_is_partial(self):
        wednesday = datetime.date(2026, 7, 22)
        self.assertTrue(data_fetch._is_partial_week("2026-07-21", today=wednesday))

    def test_prior_week_is_complete(self):
        wednesday = datetime.date(2026, 7, 22)
        self.assertFalse(data_fetch._is_partial_week("2026-07-17", today=wednesday))

    def test_weekend_treats_the_just_ended_week_as_complete(self):
        """A Friday bar shares its ISO week with the Saturday that follows.
        Without this carve-out a weekend review would always throw away
        the most recent completed week.
        """
        saturday = datetime.date(2026, 7, 25)
        self.assertEqual(saturday.isocalendar()[:2],
                         datetime.date(2026, 7, 24).isocalendar()[:2])
        self.assertFalse(data_fetch._is_partial_week("2026-07-24", today=saturday))

    def test_drop_partial_week_removes_only_the_last_bar(self):
        bars = [{"time": "2026-07-17T04:00:00.000+0000"},
                {"time": "2026-07-24T04:00:00.000+0000"}]
        original = list(bars)
        kept = data_fetch._drop_partial_week(bars, include_partial_week=True)
        self.assertEqual(kept, original)

    def test_empty_input_is_safe(self):
        self.assertEqual(data_fetch._drop_partial_week([], False), [])


class BatchUnpackTest(unittest.TestCase):
    def test_unpacks_every_symbol_oldest_first(self):
        response = _FakeResponse({"result": [
            _raw("AAA", ["2026-07-10", "2026-07-17"]),
            _raw("BBB", ["2026-07-10", "2026-07-17"]),
        ]})
        out = data_fetch._bars_from_batch_response(response)
        self.assertEqual(set(out), {"AAA", "BBB"})
        self.assertEqual(out["AAA"][0]["time"][:10], "2026-07-10")
        self.assertEqual(out["AAA"][-1]["time"][:10], "2026-07-17")

    def test_one_empty_symbol_does_not_discard_the_batch(self):
        """The single-symbol unpacker raises on empty, which is right when
        one thing was asked for and wrong for a batch of twenty.
        """
        response = _FakeResponse({"result": [
            _raw("GOOD", ["2026-07-17"]),
            {"symbol": "DEAD", "result": []},
        ]})
        out = data_fetch._bars_from_batch_response(response)
        self.assertIn("GOOD", out)
        self.assertNotIn("DEAD", out)

    def test_accepts_a_bare_array_payload(self):
        response = _FakeResponse([_raw("AAA", ["2026-07-17"])])
        self.assertIn("AAA", data_fetch._bars_from_batch_response(response))

    def test_parses_numeric_strings(self):
        out = data_fetch._bars_from_batch_response(
            _FakeResponse({"result": [_raw("AAA", ["2026-07-17"])]})
        )
        bar = out["AAA"][0]
        for field in ("open", "high", "low", "close", "volume"):
            self.assertIsInstance(bar[field], float)

    def test_batch_cap_matches_the_server_limit(self):
        self.assertEqual(data_fetch.MAX_SYMBOLS_PER_BATCH, 20)


if __name__ == "__main__":
    unittest.main()


class BatchSplitsAroundBadSymbolsTest(unittest.TestCase):
    """A single unrecognised ticker makes the server reject the whole
    request, so a batch of twenty used to die for one bad name — 100
    symbols lost across a full sweep, indistinguishable downstream from
    tickers that simply didn't qualify.
    """

    class _FakeMarketData:
        def __init__(self, bad):
            self.bad = bad
            self.calls = []

        def get_batch_history_bar(self, symbols, category, timespan, count):
            self.calls.append(list(symbols))
            offenders = [s for s in symbols if s in self.bad]
            if offenders:
                raise RuntimeError(f"INVALID_SYMBOL {offenders}")
            return _FakeResponse([
                {"symbol": s, "result": [
                    {"time": "2026-01-02T04:00:00.000+0000", "open": 1, "high": 1,
                     "low": 1, "close": 1, "volume": 1}
                ]}
                for s in symbols
            ])

    class _FakeClient:
        def __init__(self, market_data):
            self.market_data = market_data

    def test_good_symbols_survive_a_poisoned_batch(self):
        good = [f"OK{i}" for i in range(19)]
        md = self._FakeMarketData(bad={"BAD"})
        out = {}
        data_fetch._fetch_chunk(self._FakeClient(md), good + ["BAD"], 104, True, out)
        self.assertEqual(sorted(out), sorted(good))
        self.assertNotIn("BAD", out)

    def test_isolating_one_offender_is_cheaper_than_retrying_each(self):
        md = self._FakeMarketData(bad={"BAD"})
        out = {}
        chunk = [f"OK{i}" for i in range(19)] + ["BAD"]
        data_fetch._fetch_chunk(self._FakeClient(md), chunk, 104, True, out)
        self.assertLess(len(md.calls), len(chunk))

    def test_an_all_bad_batch_drops_everything_without_raising(self):
        md = self._FakeMarketData(bad={"A", "B"})
        out = {}
        data_fetch._fetch_chunk(self._FakeClient(md), ["A", "B"], 104, True, out)
        self.assertEqual(out, {})


class BarCountCapTest(unittest.TestCase):
    """The server refuses any count above 1200 outright rather than
    truncating, and the refusal used to be swallowed.

    This mattered far more than a rejected request normally would.
    run_backtest asks for enough daily bars to span the whole test
    window, so any backtest starting more than about 3.3 years back threw
    on every sector fetch, hit a bare `except`, and ran the entire test
    with condition 5 unresolved at every checkpoint — indistinguishable
    in the output from a normal run.
    """

    def test_a_request_within_the_cap_is_untouched(self):
        self.assertEqual(data_fetch._capped(104, "weekly"), 104)
        self.assertEqual(data_fetch._capped(data_fetch.MAX_BARS_PER_REQUEST, "weekly"),
                         data_fetch.MAX_BARS_PER_REQUEST)

    def test_an_oversized_request_is_clamped_rather_than_refused(self):
        self.assertEqual(data_fetch._capped(1532, "daily", "SPY"),
                         data_fetch.MAX_BARS_PER_REQUEST)

    def test_clamping_says_so(self):
        """Silent truncation would be its own version of this bug: the
        early checkpoints would resolve differently with no indication."""
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            data_fetch._capped(5000, "daily", "XLK")
        out = buf.getvalue()
        self.assertIn("5000", out)
        self.assertIn(str(data_fetch.MAX_BARS_PER_REQUEST), out)
        self.assertIn("XLK", out)

    def test_no_warning_when_nothing_is_truncated(self):
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            data_fetch._capped(300, "weekly", "AAPL")
        self.assertEqual(buf.getvalue(), "")


class DailyBarCacheTest(unittest.TestCase):
    """A backtest asks for sector data once per ticker, and every one of
    those asks refetched the identical SPY series — a third of the API
    budget spent on data already in hand."""

    def setUp(self):
        self._prev = dict(data_fetch._daily_bar_cache)
        data_fetch._daily_bar_cache.clear()
        self.calls = []

    def tearDown(self):
        data_fetch._daily_bar_cache.clear()
        data_fetch._daily_bar_cache.update(self._prev)

    def _patch(self):
        original = data_fetch.get_daily_bars

        def fake(symbol, category, lookback_days):
            self.calls.append((symbol, category, lookback_days))
            return [{"time": "2024-01-02T00:00:00.000+0000", "close": 1.0}]

        data_fetch.get_daily_bars = fake
        self.addCleanup(lambda: setattr(data_fetch, "get_daily_bars", original))

    def test_a_repeated_request_is_served_from_memory(self):
        self._patch()
        for _ in range(5):
            data_fetch._cached_daily_bars("SPY", "US_ETF", 1200)
        self.assertEqual(len(self.calls), 1)

    def test_a_different_symbol_or_lookback_is_fetched_separately(self):
        """Sharing a cache entry across lookbacks would hand back a
        series that is the wrong length for the caller's window."""
        self._patch()
        data_fetch._cached_daily_bars("SPY", "US_ETF", 1200)
        data_fetch._cached_daily_bars("XLK", "US_ETF", 1200)
        data_fetch._cached_daily_bars("SPY", "US_ETF", 600)
        self.assertEqual(len(self.calls), 3)

    def test_the_cached_value_is_what_the_fetch_returned(self):
        self._patch()
        first = data_fetch._cached_daily_bars("SPY", "US_ETF", 1200)
        second = data_fetch._cached_daily_bars("SPY", "US_ETF", 1200)
        self.assertEqual(first, second)
        self.assertEqual(first[0]["close"], 1.0)
