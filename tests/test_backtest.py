"""Backtest regressions — chiefly the no-lookahead property.

This is the one that matters most for the backtest's credibility. The
whole engine is worthless if an evaluation "as of" a past date can see
bars that hadn't happened yet, and that failure is invisible in the
output: results simply look better than they should.

The property asserted here is the strong form. Rather than checking
that truncation happens, it checks that the answer is *identical*
whether or not future data was ever present in the input. If any future
bar leaked into a calculation, the two would diverge.
"""
import unittest

from screener import backtest, stop_loss
from tests.synthetic import bar, daily_dates, trending_bars, weekly_dates


def _flat_bars(n, price=100.0):
    """A quiet series — enough bars to warm the indicators, no setup."""
    return [bar(d, price * 1.01, price * 0.99, price) for d in weekly_dates(n, "2019-01-04")]


def _sector(daily_bars_a, daily_bars_b):
    return {"sector": "Oil & Gas", "sector_etf_bars": daily_bars_a, "spy_bars": daily_bars_b}


class NoLookaheadTest(unittest.TestCase):
    def setUp(self):
        self.bars = trending_bars(150, 100.0, 0.7)
        self.index = trending_bars(150, 400.0, 0.3)
        self.etf = trending_bars(300, 50.0, 0.05, start="2023-01-03", daily=True)
        self.spy = trending_bars(300, 400.0, 0.04, start="2023-01-03", daily=True)

    def _truncate(self, bars, as_of):
        return [b for b in bars if b["time"][:10] <= as_of]

    def test_future_bars_cannot_change_an_as_of_evaluation(self):
        for idx in (60, 80, 100, 120):
            as_of = self.bars[idx]["time"][:10]

            with_future = backtest.evaluate_as_of(
                "T", as_of, self.bars, self.index, _sector(self.etf, self.spy)
            )
            without_future = backtest.evaluate_as_of(
                "T", as_of,
                self._truncate(self.bars, as_of), self._truncate(self.index, as_of),
                _sector(self._truncate(self.etf, as_of), self._truncate(self.spy, as_of)),
            )

            self.assertEqual(with_future["conditions"], without_future["conditions"], as_of)
            self.assertEqual(with_future["scoring"], without_future["scoring"], as_of)
            self.assertEqual(with_future["breakout_idx"], without_future["breakout_idx"], as_of)
            self.assertEqual(with_future["swing_stop"], without_future["swing_stop"], as_of)
            self.assertEqual(with_future["bars_used"], without_future["bars_used"], as_of)

    def test_sector_snapshot_is_never_used_for_a_past_date(self):
        """The live sector-overview figure has no as-of parameter, so using
        today's value for a historical date would be lookahead rather than
        imprecision. It must stay None.
        """
        as_of = self.bars[100]["time"][:10]
        result = backtest.evaluate_as_of(
            "T", as_of, self.bars, self.index, _sector(self.etf, self.spy)
        )
        detail = result["conditions_detail"]["sector_strength"]
        self.assertIsNone(detail.get("sector_strength_pct"))


class TruncationTest(unittest.TestCase):
    def test_keeps_the_as_of_date_itself(self):
        bars = trending_bars(10)
        as_of = bars[4]["time"][:10]
        kept = backtest._truncate_bars(bars, as_of)
        self.assertEqual(len(kept), 5)
        self.assertEqual(kept[-1]["time"][:10], as_of)


class SimulateTradeTest(unittest.TestCase):
    def _bars(self, closes):
        dates = weekly_dates(len(closes))
        return [bar(d, c * 1.02, c * 0.98, c) for d, c in zip(dates, closes)]

    def test_stop_exit_is_capped_at_one_r(self):
        """A stop-out should lose about the risk that was defined up front.
        Losing materially more means the stop isn't being honoured.
        """
        closes = [100.0] * 10 + [95.0, 90.0, 85.0, 80.0, 75.0]
        bars = self._bars(closes)
        entry_date = bars[9]["time"][:10]
        trade = backtest.simulate_trade(
            "T", entry_date, 100.0, swing_stop=95.0, swing_target=130.0, bars_full=bars,
        )
        self.assertEqual(trade["exit_reason"], "stop")
        self.assertLessEqual(trade["r_multiple"], 0.0)
        self.assertGreaterEqual(trade["r_multiple"], -1.6)

    def test_unresolved_trade_reports_still_open_without_inventing_a_return(self):
        closes = [100.0 + i * 0.05 for i in range(20)]
        bars = self._bars(closes)
        trade = backtest.simulate_trade(
            "T", bars[2]["time"][:10], bars[2]["close"],
            swing_stop=50.0, swing_target=500.0, bars_full=bars, max_hold_weeks=5,
        )
        self.assertTrue(trade["still_open"])
        self.assertIsNone(trade["return_pct"])
        self.assertIsNone(trade["r_multiple"])

    def test_unknown_entry_date_returns_none(self):
        self.assertIsNone(
            backtest.simulate_trade("T", "1999-01-01", 10.0, 9.0, 12.0, self._bars([10.0] * 5))
        )


class PartialProfitTakingTest(unittest.TestCase):
    """The target sells part of the position; the rest rides the trailing
    stop. Exiting fully at the target truncated every winner at its own
    measured objective, which quietly turned a trend-following method
    into a fixed-target one — and nothing in the suite covered the target
    path at all, which is why it went unnoticed.
    """

    def _bars(self, closes):
        dates = weekly_dates(len(closes))
        return [bar(d, c * 1.02, c * 0.98, c) for d, c in zip(dates, closes)]

    TARGET = 120.0

    def _run_past_target(self, **kw):
        # A 40-week warm-up so the 30-week MA the trailing stop rides
        # actually exists, then entry, a rally clean through the target,
        # and a decline deep enough to take the remainder out.
        closes = (
            [60.0 + i for i in range(40)]
            + [110.0, 125.0, 150.0, 175.0, 200.0, 160.0, 140.0, 120.0, 100.0, 95.0]
        )
        bars = self._bars(closes)
        return backtest.simulate_trade(
            "T", bars[39]["time"][:10], closes[39],
            swing_stop=90.0, swing_target=self.TARGET, bars_full=bars, **kw
        )

    def test_reaching_the_target_does_not_close_the_position(self):
        trade = self._run_past_target()
        self.assertEqual(trade["exit_reason"], "target_then_stop")
        # Exited later and lower than the target, which can only happen
        # if the remainder kept running after the target was reached.
        self.assertNotAlmostEqual(trade["exit_price"], self.TARGET, places=6)

    def test_blend_is_the_position_weighted_average_of_the_two_legs(self):
        """Verified against the ends of the range rather than an assumed
        remainder price: selling none must equal the trailing-stop exit,
        selling all must equal the target, and half must sit exactly
        between them."""
        none_taken = self._run_past_target(partial_exit_fraction=0.0)["exit_price"]
        all_taken = self._run_past_target(partial_exit_fraction=1.0)["exit_price"]
        half_taken = self._run_past_target(partial_exit_fraction=0.5)["exit_price"]

        self.assertAlmostEqual(all_taken, self.TARGET, places=6)
        self.assertAlmostEqual(half_taken, 0.5 * all_taken + 0.5 * none_taken, places=6)

    def test_the_module_default_is_patchable(self):
        """The fraction has to be read at call time. Bound as a default
        argument it fixes at import, so patching it to compare exit
        policies changes nothing and both arms of the A/B run identically
        — which looks like a null result rather than a broken test.
        """
        original = backtest.PARTIAL_EXIT_FRACTION
        try:
            backtest.PARTIAL_EXIT_FRACTION = 1.0
            self.assertAlmostEqual(self._run_past_target()["exit_price"], self.TARGET, places=6)
            backtest.PARTIAL_EXIT_FRACTION = 0.0
            self.assertNotAlmostEqual(self._run_past_target()["exit_price"], self.TARGET, places=6)
        finally:
            backtest.PARTIAL_EXIT_FRACTION = original

    def test_the_fraction_moves_the_blend_monotonically(self):
        prices = [
            self._run_past_target(partial_exit_fraction=f)["exit_price"]
            for f in (0.0, 0.25, 0.5, 0.75, 1.0)
        ]
        self.assertEqual(prices, sorted(prices), "blend should move steadily toward the target")

    def test_stopping_before_the_target_is_unaffected(self):
        closes = [100.0] * 5 + [95.0, 88.0, 80.0]
        bars = self._bars(closes)
        trade = backtest.simulate_trade(
            "T", bars[4]["time"][:10], 100.0,
            swing_stop=95.0, swing_target=130.0, bars_full=bars,
        )
        self.assertEqual(trade["exit_reason"], "stop")

    def test_a_banked_partial_does_not_make_an_open_trade_scoreable(self):
        """Half realised and half still running is not a finished trade;
        counting the unrealised remainder would flatter the result."""
        closes = [100.0] * 5 + [130.0, 135.0, 140.0]
        bars = self._bars(closes)
        trade = backtest.simulate_trade(
            "T", bars[4]["time"][:10], 100.0,
            swing_stop=90.0, swing_target=120.0, bars_full=bars, max_hold_weeks=3,
        )
        self.assertTrue(trade["still_open"])
        self.assertEqual(trade["exit_reason"], "target_then_open")
        self.assertIsNone(trade["return_pct"])


class TrailingStopTest(unittest.TestCase):
    def test_stop_ratchets_and_never_retreats(self):
        """A trailing stop that can move down isn't a trailing stop."""
        bars = trending_bars(120, 100.0, 1.5)
        entry_idx = 60
        previous = None
        for end in range(entry_idx + 5, len(bars) + 1, 5):
            trail = stop_loss.trailing_stop(bars[:end], bars[entry_idx]["close"], entry_idx)
            current = trail["ma_stop"]
            if current is not None and previous is not None:
                self.assertGreaterEqual(current, previous - 1e-9)
            if current is not None:
                previous = current

    def test_out_of_range_entry_returns_none(self):
        bars = trending_bars(20)
        self.assertIsNone(stop_loss.trailing_stop(bars, 100.0, None))
        self.assertIsNone(stop_loss.trailing_stop(bars, 100.0, 999))

    def test_short_side_ratchets_downward(self):
        bars = trending_bars(120, 200.0, -1.2)
        entry_idx = 60
        previous = None
        for end in range(entry_idx + 5, len(bars) + 1, 5):
            trail = stop_loss.short_trailing_stop(bars[:end], bars[entry_idx]["close"], entry_idx)
            current = trail["ma_stop"]
            if current is not None and previous is not None:
                self.assertLessEqual(current, previous + 1e-9)
            if current is not None:
                previous = current


if __name__ == "__main__":
    unittest.main()


class CacheBackedRunTest(unittest.TestCase):
    """Reading bars from a local cache instead of the API.

    Network was the dominant cost of a wide run and it was spent
    re-fetching history already on disk. The risks introduced are both
    silent ones: a symbol missing from the cache looking like a symbol
    that never qualified, and a partial cache quietly falling back to
    the network and costing hours.
    """

    def setUp(self):
        self._real_weekly = backtest.data_fetch.get_weekly_bars
        self._real_index = backtest.data_fetch.get_index_bars
        self._real_sector = backtest.data_fetch.get_sector_data_for_backtest
        self.weekly_calls = []
        self.sector_calls = []

        def no_weekly(ticker, **kw):
            self.weekly_calls.append(ticker)
            raise AssertionError(f"went to the network for {ticker} despite a cache")

        def no_sector(ticker, *a, **kw):
            self.sector_calls.append(ticker)
            return {"sector": None, "sector_etf_bars": [], "spy_bars": []}

        backtest.data_fetch.get_weekly_bars = no_weekly
        backtest.data_fetch.get_index_bars = lambda *a, **kw: _flat_bars(300)
        backtest.data_fetch.get_sector_data_for_backtest = no_sector

    def tearDown(self):
        backtest.data_fetch.get_weekly_bars = self._real_weekly
        backtest.data_fetch.get_index_bars = self._real_index
        backtest.data_fetch.get_sector_data_for_backtest = self._real_sector

    def test_cached_symbols_never_touch_the_network(self):
        cache = {"AAA": _flat_bars(300), "SPY": _flat_bars(300)}
        backtest.run_backtest(["AAA"], "2024-01-05", "2024-06-07",
                              bars_by_symbol=cache, fetch_sector=False,
                              parameter_set="test_cache")
        self.assertEqual(self.weekly_calls, [])

    def test_a_symbol_absent_from_the_cache_is_skipped_not_fetched(self):
        cache = {"AAA": _flat_bars(300), "SPY": _flat_bars(300)}
        backtest.run_backtest(["AAA", "MISSING"], "2024-01-05", "2024-06-07",
                              bars_by_symbol=cache, fetch_sector=False,
                              parameter_set="test_cache")
        self.assertEqual(self.weekly_calls, [],
                         "a cache miss must not silently go to the network")

    def test_fetch_sector_false_skips_the_sector_lookup(self):
        """Condition 5 cannot resolve before ~2021 anyway, so paying one
        call per ticker for it is spending money to learn nothing."""
        cache = {"AAA": _flat_bars(300), "SPY": _flat_bars(300)}
        backtest.run_backtest(["AAA"], "2024-01-05", "2024-06-07",
                              bars_by_symbol=cache, fetch_sector=False,
                              parameter_set="test_cache")
        self.assertEqual(self.sector_calls, [])

    def test_fetch_sector_true_still_looks_it_up(self):
        cache = {"AAA": _flat_bars(300), "SPY": _flat_bars(300)}
        backtest.run_backtest(["AAA"], "2024-01-05", "2024-06-07",
                              bars_by_symbol=cache, fetch_sector=True,
                              parameter_set="test_cache")
        self.assertEqual(self.sector_calls, ["AAA"])

    def test_skipped_symbols_are_reported_out_loud(self):
        import contextlib, io
        cache = {"SPY": _flat_bars(300)}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            backtest.run_backtest(["GONE"], "2024-01-05", "2024-06-07",
                                  bars_by_symbol=cache, fetch_sector=False,
                                  parameter_set="test_cache")
        self.assertIn("skipped", buf.getvalue())


class EntryPriceTest(unittest.TestCase):
    """Where a simulated fill happens.

    The engine used to fill at the breakout bar regardless of when the
    signal fired. Scans find a breakout a median of four weeks after it
    happened, so that books a rise which had already occurred — measured
    at +1.11 points a trade across the 273-trade study, which was the
    entire measured edge. The decision was always point-in-time clean;
    the fill price was not.
    """

    def test_signal_fills_are_never_earlier_than_the_signal(self):
        idx = backtest._bar_index_on_or_before(_flat_bars(50), "2019-06-07")
        bars = _flat_bars(50)
        self.assertLessEqual(bars[idx]["time"][:10], "2019-06-07")
        self.assertGreater(bars[idx + 1]["time"][:10], "2019-06-07")

    def test_a_date_before_every_bar_has_no_index(self):
        self.assertIsNone(backtest._bar_index_on_or_before(_flat_bars(50), "1990-01-01"))

    def test_a_date_after_every_bar_returns_the_last(self):
        bars = _flat_bars(50)
        self.assertEqual(backtest._bar_index_on_or_before(bars, "2099-01-01"), len(bars) - 1)

    def test_the_two_entry_modes_price_differently_on_a_risen_stock(self):
        """The whole point: if price rose between breakout and signal,
        filling at the breakout is a price no longer available."""
        dates = weekly_dates(60, "2019-01-04")
        rising = [bar(d, 100 + i * 2, 98 + i * 2, 99 + i * 2) for i, d in enumerate(dates)]
        early = backtest._bar_index_on_or_before(rising, dates[20])
        late = backtest._bar_index_on_or_before(rising, dates[40])
        self.assertLess(rising[early]["close"], rising[late]["close"],
                        "a rising series must price later fills higher")

    def test_default_is_the_conservative_mode(self):
        import inspect
        sig = inspect.signature(backtest.run_backtest)
        self.assertEqual(sig.parameters["entry_at"].default, "signal")


class EntryModeIntegrationTest(unittest.TestCase):
    """End-to-end: which bar run_backtest actually fills on.

    Testing the helper alone was not enough — a mutation swapping the
    call for `entry_idx = breakout_idx` passed the whole suite, because
    nothing checked what the engine did with it.
    """

    def setUp(self):
        self._real_eval = backtest.evaluate_as_of
        self._real_index = backtest.data_fetch.get_index_bars
        backtest.data_fetch.get_index_bars = lambda *a, **kw: _flat_bars(200)
        self.bars = [bar(d, 100 + i, 98 + i, 99 + i)
                     for i, d in enumerate(weekly_dates(200, "2019-01-04"))]
        # A breakout long before any checkpoint, so the two modes must
        # disagree if the engine honours entry_at at all.
        self.breakout_idx = 100

        def fake_eval(ticker, as_of_date, bars_full, index_bars, sector):
            return {"actionable": True, "breakout_idx": self.breakout_idx,
                    "swing_stop": 50.0, "swing_target": 400.0,
                    "conditions_met": 9, "as_of_date": as_of_date}

        backtest.evaluate_as_of = fake_eval

    def tearDown(self):
        backtest.evaluate_as_of = self._real_eval
        backtest.data_fetch.get_index_bars = self._real_index

    def _run(self, mode):
        cache = {"AAA": self.bars}
        return backtest.run_backtest(
            ["AAA"], self.bars[150]["time"][:10], self.bars[190]["time"][:10],
            check_interval_weeks=4, parameter_set=f"entrymode_{mode}",
            bars_by_symbol=cache, fetch_sector=False, entry_at=mode)

    def test_signal_mode_fills_at_the_checkpoint_not_the_breakout(self):
        trades = self._run("signal")
        self.assertTrue(trades, "expected a trade")
        t = trades[0]
        self.assertEqual(t["entry_date"], t["as_of_date"],
                         "signal mode must fill on the signal bar")
        self.assertGreater(t["entry_price"], self.bars[self.breakout_idx]["close"],
                           "a risen series must fill higher than the old breakout")

    def test_breakout_mode_reproduces_the_old_behaviour(self):
        trades = self._run("breakout")
        self.assertTrue(trades)
        t = trades[0]
        self.assertEqual(t["entry_date"], self.bars[self.breakout_idx]["time"][:10])
        self.assertLess(t["entry_date"], t["as_of_date"])

    def test_the_two_modes_disagree_on_price(self):
        a = self._run("signal")[0]["entry_price"]
        b = self._run("breakout")[0]["entry_price"]
        self.assertNotEqual(a, b, "if these match the parameter does nothing")


class ExtensionProfitTakingTest(unittest.TestCase):
    """R5: the book's second rule about stocks far above their average.

    Its answer to a position that has skyrocketed is not "don't buy" —
    that's the entry rule — but "take part of it off and trail the rest".
    Distinct from every other candidate tested because it removes no
    trades, so it cannot destroy the winners by excluding them.
    """

    def _runaway(self, n=80):
        """Flat, then a violent advance far above the average."""
        dates = weekly_dates(n, "2019-01-04")
        out = []
        for i, d in enumerate(dates):
            price = 100.0 if i < 50 else 100.0 * (1 + 0.10 * (i - 49))
            out.append(bar(d, price * 1.02, price * 0.98, price))
        return out

    def test_disabled_by_default(self):
        bars = self._runaway()
        t = backtest.simulate_trade("AAA", bars[50]["time"][:10], bars[50]["close"],
                                    50.0, None, bars, max_hold_weeks=30)
        self.assertIsNotNone(t)
        self.assertNotEqual(t["exit_reason"], "target_then_stop",
                            "no target and no rule armed: nothing should bank early")

    def test_it_banks_part_of_the_position_when_price_runs_far_above_the_average(self):
        bars = self._runaway()
        t = backtest.simulate_trade("AAA", bars[50]["time"][:10], bars[50]["close"],
                                    50.0, None, bars, max_hold_weeks=30,
                                    take_profit_above_ma_pct=40.0)
        self.assertIsNotNone(t)
        self.assertIn(t["exit_reason"], ("target_then_stop", "target_then_open"),
                      "a runaway advance should have triggered a partial exit")

    def test_a_stock_that_never_extends_is_untouched(self):
        dates = weekly_dates(80, "2019-01-04")
        flat = [bar(d, 101.0, 99.0, 100.0) for d in dates]
        a = backtest.simulate_trade("AAA", flat[50]["time"][:10], 100.0, 50.0, None,
                                    flat, max_hold_weeks=25)
        b = backtest.simulate_trade("AAA", flat[50]["time"][:10], 100.0, 50.0, None,
                                    flat, max_hold_weeks=25, take_profit_above_ma_pct=40.0)
        self.assertEqual(a["exit_reason"], b["exit_reason"])
        self.assertAlmostEqual(a["return_pct"], b["return_pct"], places=6)

    def _spike_then_collapse(self, n=90):
        """Rises hard, then gives it all back — so the stop actually
        fires and the trade resolves. A series that only ever rises
        leaves both arms open with a null return, which compares equal
        and looks like the rule doing nothing."""
        dates = weekly_dates(n, "2019-01-04")
        out = []
        for i, d in enumerate(dates):
            if i < 50:
                price = 100.0
            elif i < 70:
                price = 100.0 * (1 + 0.10 * (i - 49))
            else:
                price = 300.0 * (1 - 0.08 * (i - 69))
            out.append(bar(d, price * 1.02, price * 0.98, price))
        return out

    def test_a_lower_threshold_banks_earlier(self):
        bars = self._spike_then_collapse()
        early = backtest.simulate_trade("AAA", bars[50]["time"][:10], bars[50]["close"],
                                        50.0, None, bars, max_hold_weeks=40,
                                        take_profit_above_ma_pct=20.0)
        late = backtest.simulate_trade("AAA", bars[50]["time"][:10], bars[50]["close"],
                                       50.0, None, bars, max_hold_weeks=40,
                                       take_profit_above_ma_pct=200.0)
        self.assertIsNotNone(early["return_pct"], "trade must resolve to be comparable")
        self.assertIsNotNone(late["return_pct"])
        self.assertNotEqual(early["return_pct"], late["return_pct"],
                            "if thresholds give identical results the rule is inert")

    # Deliberately not tested: whether banking early beats riding the
    # position. I wrote that assertion and it failed — on this fixture
    # riding returned +71.5% against +46.0%, because a 30% threshold
    # banks half the position while the average is still low and the
    # trailing stop then carries the rest much higher. That is a claim
    # about markets, not about code, and baking an answer to it into a
    # test would prejudge the very thing R5 exists to measure. The
    # changelog already records making this mistake once with the
    # partial-exit tests; the rule here is that tests assert mechanics
    # and the backtest answers the market question.


class MAStopBufferTest(unittest.TestCase):
    """The book says to place the stop *below* the 30-week average. This
    code placed it exactly on the line, which is materially tighter —
    any pullback that touches the average closes the position. That is
    the mechanism behind a 2% capture rate on stocks that averaged +270%.
    """

    def setUp(self):
        self._prev = stop_loss.MA_STOP_BUFFER_PCT

    def tearDown(self):
        stop_loss.MA_STOP_BUFFER_PCT = self._prev

    def _rising(self, n=90):
        dates = weekly_dates(n, "2019-01-04")
        out, price = [], 100.0
        for d in dates:
            out.append(bar(d, price * 1.03, price * 0.97, price))
            price *= 1.01
        return out

    def test_defaults_to_zero_so_behaviour_is_unchanged(self):
        self.assertEqual(self._prev, 0.0)

    def test_a_buffer_places_the_stop_below_the_average(self):
        bars = self._rising()
        stop_loss.MA_STOP_BUFFER_PCT = 0.0
        on_line = stop_loss.trailing_stop(bars, bars[40]["close"], 40, method="ma")
        stop_loss.MA_STOP_BUFFER_PCT = 8.0
        below = stop_loss.trailing_stop(bars, bars[40]["close"], 40, method="ma")
        self.assertIsNotNone(on_line["recommended"])
        self.assertIsNotNone(below["recommended"])
        self.assertLess(below["recommended"], on_line["recommended"],
                        "a buffer must lower the stop, not leave it on the line")

    def test_a_looser_stop_survives_a_pullback_that_would_have_closed(self):
        """The whole point: room to gyrate while the trend is intact."""
        bars = self._rising()
        stop_loss.MA_STOP_BUFFER_PCT = 0.0
        tight = stop_loss.trailing_stop(bars, bars[40]["close"], 40, method="ma")["recommended"]
        stop_loss.MA_STOP_BUFFER_PCT = 10.0
        loose = stop_loss.trailing_stop(bars, bars[40]["close"], 40, method="ma")["recommended"]
        dip = tight * 0.98          # a pullback through the tight stop
        self.assertLess(dip, tight, "fixture must actually breach the tight stop")
        self.assertGreater(dip, loose, "the looser stop must survive it")


class ShortTradeTest(unittest.TestCase):
    """simulate_short_trade is its own function, not simulate_trade with
    negated inputs. The geometry inverts in ways sign-flipping gets
    subtly wrong: the stop sits above entry and ratchets down, the target
    sits below, and profit is (entry - exit)."""

    def _falling(self, n=80, start=200.0, rate=0.02):
        dates = weekly_dates(n, "2019-01-04")
        out, price = [], start
        for d in dates:
            out.append(bar(d, price * 1.02, price * 0.98, price))
            price *= (1 - rate)
        return out

    def _rising(self, n=80, start=100.0, rate=0.03):
        dates = weekly_dates(n, "2019-01-04")
        out, price = [], start
        for d in dates:
            out.append(bar(d, price * 1.02, price * 0.98, price))
            price *= (1 + rate)
        return out

    def test_a_falling_stock_is_profitable_to_be_short(self):
        bars = self._falling()
        entry = bars[40]["close"]
        t = backtest.simulate_short_trade("AAA", bars[40]["time"][:10], entry,
                                          entry * 1.10, entry * 0.5, bars)
        self.assertIsNotNone(t)
        self.assertGreater(t["return_pct"], 0,
                           "short profit is entry minus exit")

    def test_a_rising_stock_stops_the_short_out_for_a_loss(self):
        bars = self._rising()
        entry = bars[40]["close"]
        t = backtest.simulate_short_trade("AAA", bars[40]["time"][:10], entry,
                                          entry * 1.10, entry * 0.5, bars)
        self.assertIsNotNone(t)
        self.assertLess(t["return_pct"], 0)
        self.assertEqual(t["exit_reason"], "stop")

    def test_the_loss_is_bounded_by_the_buy_stop(self):
        """The book's own point: a short at 40 with a buy-stop at 44 risks
        10%, exactly as a long at 40 stopped at 36 does. 'Unlimited risk'
        does not survive a protective stop."""
        bars = self._rising(rate=0.10)      # violent advance against us
        entry = bars[40]["close"]
        t = backtest.simulate_short_trade("AAA", bars[40]["time"][:10], entry,
                                          entry * 1.10, entry * 0.5, bars)
        self.assertGreater(t["return_pct"], -11.0,
                           "loss must be capped near the 10% buy-stop")

    def test_the_stop_ratchets_down_never_up(self):
        """The mirror of the long side's up-only rule.

        The distinguishing case is a decline followed by a bounce. A stop
        that has trailed down gets hit by the bounce and banks the gain;
        one that only moved up sits too high to trigger and the position
        rides back to break-even. Asserting merely that the exit is below
        the initial stop passes either way — my first version did, and a
        mutation reversing the comparison survived it.
        """
        dates = weekly_dates(80, "2019-01-04")
        closes, price = [], 200.0
        for i in range(80):
            if i < 55:
                price *= 0.97          # sustained decline
            else:
                price *= 1.05          # sharp bounce back
            closes.append(price)
        bars = [bar(d, c * 1.02, c * 0.98, c) for d, c in zip(dates, closes)]
        entry = bars[20]["close"]
        t = backtest.simulate_short_trade("AAA", bars[20]["time"][:10], entry,
                                          entry * 1.10, None, bars,
                                          max_hold_weeks=60)
        self.assertIsNotNone(t)
        self.assertFalse(t["still_open"], "the bounce should have covered the short")
        self.assertGreater(t["return_pct"], 0,
                           "a trailed stop banks the decline; an untrailed one gives it back")
        self.assertLess(t["exit_price"], entry,
                        "the covering stop must have trailed below the entry")

    def test_it_is_tagged_as_a_short(self):
        bars = self._falling()
        t = backtest.simulate_short_trade("AAA", bars[40]["time"][:10],
                                          bars[40]["close"], bars[40]["close"] * 1.1,
                                          None, bars)
        self.assertEqual(t["direction"], "short")

    def test_an_unknown_entry_date_returns_none(self):
        self.assertIsNone(backtest.simulate_short_trade(
            "AAA", "1990-01-01", 100.0, 110.0, 50.0, self._falling()))


class ShortRunnerTest(unittest.TestCase):
    """run_short_backtest walks the same structure as the long runner but
    evaluates the short checklist and simulates a short."""

    def setUp(self):
        self._real_eval = None
        self._real_index = backtest.data_fetch.get_index_bars
        backtest.data_fetch.get_index_bars = lambda *a, **kw: _flat_bars(300)
        from screener import short_conditions
        self.sc = short_conditions
        self._real_short_eval = short_conditions.evaluate_short_conditions

    def tearDown(self):
        backtest.data_fetch.get_index_bars = self._real_index
        self.sc.evaluate_short_conditions = self._real_short_eval

    def _falling_bars(self, n=200):
        dates = weekly_dates(n, "2019-01-04")
        out, price = [], 300.0
        for d in dates:
            out.append(bar(d, price * 1.02, price * 0.98, price))
            price *= 0.985
        return out

    def _patch_eval(self, buy_stop_factor, actionable=True):
        bars = self._falling_bars()

        def fake(ticker, b, idx, sector):
            price = b[-1]["close"] if b else 100.0
            return {"scoring": {"actionable": actionable}, "conditions_met": 7,
                    "buy_stop": price * buy_stop_factor, "target": price * 0.5}

        self.sc.evaluate_short_conditions = fake
        return bars

    def test_it_produces_short_trades(self):
        bars = self._patch_eval(1.10)
        trades = backtest.run_short_backtest(
            ["AAA"], bars[100]["time"][:10], bars[180]["time"][:10],
            parameter_set="test_shortrunner", bars_by_symbol={"AAA": bars, "SPY": bars},
            fetch_sector=False)
        self.assertTrue(trades)
        self.assertEqual(trades[0]["direction"], "short")

    def test_a_stop_below_the_entry_is_refused_not_invented(self):
        """A short's protective stop must sit above entry. A level read
        that puts it below describes a malformed setup, and guessing a
        replacement would manufacture a trade that never existed."""
        bars = self._patch_eval(0.90)      # stop below entry — malformed
        trades = backtest.run_short_backtest(
            ["AAA"], bars[100]["time"][:10], bars[180]["time"][:10],
            parameter_set="test_shortrunner_bad",
            bars_by_symbol={"AAA": bars, "SPY": bars}, fetch_sector=False)
        self.assertEqual(trades, [])

    def test_a_non_actionable_verdict_produces_nothing(self):
        bars = self._patch_eval(1.10, actionable=False)
        trades = backtest.run_short_backtest(
            ["AAA"], bars[100]["time"][:10], bars[180]["time"][:10],
            parameter_set="test_shortrunner_none",
            bars_by_symbol={"AAA": bars, "SPY": bars}, fetch_sector=False)
        self.assertEqual(trades, [])

    def test_entries_are_never_before_the_signal(self):
        bars = self._patch_eval(1.10)
        trades = backtest.run_short_backtest(
            ["AAA"], bars[100]["time"][:10], bars[180]["time"][:10],
            parameter_set="test_shortrunner_dates",
            bars_by_symbol={"AAA": bars, "SPY": bars}, fetch_sector=False)
        for t in trades:
            self.assertLessEqual(t["entry_date"], t["as_of_date"])
