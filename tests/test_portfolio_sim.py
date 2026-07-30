"""Regressions for the account simulation.

Every number here is hand-computable on purpose. This module turns trade
lists into the headline figure I'd actually decide on — "does this beat
buying the index" — so an arithmetic slip here is worse than a wrong
threshold elsewhere: it wouldn't look wrong, it would just quietly
change the answer.
"""
import unittest

from screener import portfolio_sim


def _trade(entry, exit_date, pct, ticker="AAA", still_open=0):
    return {"ticker": ticker, "entry_date": entry, "exit_date": exit_date,
            "return_pct": pct, "still_open": still_open}


class ResolvedTradesTest(unittest.TestCase):
    def test_open_trades_are_excluded_not_counted_as_zero(self):
        """Counting an unfinished trade as a 0% result would dilute every
        average with something that hasn't happened yet."""
        trades = [_trade("2024-01-05", "2024-06-07", 10.0),
                  {"ticker": "BBB", "entry_date": "2024-02-02", "exit_date": None,
                   "return_pct": None, "still_open": 1}]
        summary = portfolio_sim.summarise_trades(trades)
        self.assertEqual(summary["n"], 1)
        self.assertEqual(summary["still_open"], 1)
        self.assertAlmostEqual(summary["mean_pct"], 10.0)

    def test_the_still_open_flag_alone_excludes_a_trade(self):
        """An open position carries a mark-to-market exit date and return
        in the real table — exit_reason 'still_open' — so the flag has to
        do the work on its own. Testing this with a null exit_date, as I
        first did, passes whether or not the flag is read at all.
        """
        trades = [_trade("2024-01-05", "2024-06-07", 10.0),
                  _trade("2024-01-05", "2024-06-07", 500.0, ticker="OPEN", still_open=1)]
        summary = portfolio_sim.summarise_trades(trades)
        self.assertEqual(summary["n"], 1, "the open trade must not be counted")
        self.assertAlmostEqual(summary["mean_pct"], 10.0)

    def test_no_resolved_trades_returns_none_rather_than_dividing_by_zero(self):
        self.assertIsNone(portfolio_sim.summarise_trades([]))
        self.assertIsNone(portfolio_sim.simulate_account([]))


class PerTradeTest(unittest.TestCase):
    def test_profit_on_a_fixed_stake_is_arithmetic(self):
        """$1,000 into +10% and -5% = +$100 and -$50 = +$50 on $2,000."""
        trades = [_trade("2024-01-05", "2024-03-01", 10.0),
                  _trade("2024-01-05", "2024-03-01", -5.0, ticker="BBB")]
        s = portfolio_sim.summarise_trades(trades, stake=1000.0)
        self.assertAlmostEqual(s["total_profit"], 50.0)
        self.assertAlmostEqual(s["capital_deployed"], 2000.0)
        self.assertAlmostEqual(s["roi_on_deployed"], 2.5)

    def test_win_rate_and_payoff(self):
        """Two +20% wins against two -10% losses: right half the time,
        and the average winner is twice the average loser."""
        trades = [_trade("2024-01-05", "2024-03-01", 20.0),
                  _trade("2024-01-05", "2024-03-01", 20.0),
                  _trade("2024-01-05", "2024-03-01", -10.0),
                  _trade("2024-01-05", "2024-03-01", -10.0)]
        s = portfolio_sim.summarise_trades(trades)
        self.assertAlmostEqual(s["win_rate"], 50.0)
        self.assertAlmostEqual(s["payoff"], 2.0)

    def test_median_and_mean_can_disagree(self):
        """The whole reason both are reported: one big winner drags the
        average positive while most trades lose money."""
        trades = [_trade("2024-01-05", "2024-03-01", -5.0) for _ in range(4)]
        trades.append(_trade("2024-01-05", "2024-03-01", 100.0))
        s = portfolio_sim.summarise_trades(trades)
        self.assertLess(s["median_pct"], 0)
        self.assertGreater(s["mean_pct"], 0)

    def test_concentration_is_reported(self):
        """If five trades made all the money, the result is those five
        names rather than the strategy."""
        trades = [_trade("2024-01-05", "2024-03-01", -1.0) for _ in range(20)]
        trades += [_trade("2024-01-05", "2024-03-01", 100.0) for _ in range(5)]
        s = portfolio_sim.summarise_trades(trades)
        self.assertGreater(s["top5_share"], 100.0)


class AccountTest(unittest.TestCase):
    def test_peak_positions_drives_the_capital_requirement(self):
        """Three trades overlapping at once needs three stakes on hand;
        three run back-to-back needs one."""
        overlapping = [_trade("2024-01-05", "2024-06-07", 5.0),
                       _trade("2024-01-12", "2024-06-07", 5.0, ticker="B"),
                       _trade("2024-01-19", "2024-06-07", 5.0, ticker="C")]
        sequential = [_trade("2024-01-05", "2024-02-02", 5.0),
                      _trade("2024-02-09", "2024-03-08", 5.0, ticker="B"),
                      _trade("2024-03-15", "2024-04-12", 5.0, ticker="C")]
        self.assertEqual(portfolio_sim.simulate_account(overlapping)["peak_positions"], 3)
        self.assertEqual(portfolio_sim.simulate_account(sequential)["peak_positions"], 1)

    def test_total_return_is_profit_over_the_capital_you_needed(self):
        """Two overlapping trades need $2,000 on hand. Making $300 on
        that is 15%, not 30% and not 7.5% — the denominator is the whole
        question, so it gets asserted rather than assumed."""
        trades = [_trade("2024-01-05", "2024-06-07", 20.0),
                  _trade("2024-01-12", "2024-06-07", 10.0, ticker="B")]
        acct = portfolio_sim.simulate_account(trades, stake=1000.0)
        self.assertAlmostEqual(acct["capital_required"], 2000.0)
        self.assertAlmostEqual(acct["realised_profit"], 300.0)
        self.assertAlmostEqual(acct["total_return_pct"], 15.0)

    def test_average_capital_is_below_peak_when_trades_do_not_overlap(self):
        """The point of reporting both: sequential trades never tie up
        three stakes, so judging them against three would understate."""
        sequential = [_trade("2024-01-05", "2024-02-02", 5.0),
                      _trade("2024-06-07", "2024-07-05", 5.0, ticker="B")]
        acct = portfolio_sim.simulate_account(sequential)
        self.assertLess(acct["avg_capital"], acct["capital_required"])

    def test_a_doubling_over_one_year_is_about_100_percent_a_year(self):
        """One trade, one stake, +100% over roughly a year."""
        acct = portfolio_sim.simulate_account(
            [_trade("2024-01-05", "2025-01-03", 100.0)], stake=1000.0)
        self.assertAlmostEqual(acct["realised_profit"], 1000.0)
        self.assertAlmostEqual(acct["cagr_pct"], 100.0, delta=1.0)

    def test_the_same_gain_over_two_years_annualises_to_less(self):
        """The reason a raw total is not a return: time matters."""
        one = portfolio_sim.simulate_account([_trade("2024-01-05", "2025-01-03", 100.0)])
        two = portfolio_sim.simulate_account([_trade("2024-01-05", "2026-01-02", 100.0)])
        self.assertAlmostEqual(one["total_return_pct"], two["total_return_pct"])
        self.assertLess(two["cagr_pct"], one["cagr_pct"])

    def test_worst_drawdown_measures_the_losing_streak(self):
        """Up $500, then down $800, then recovering: the pain is -$800,
        not the -$300 you end up with."""
        trades = [_trade("2024-01-05", "2024-02-02", 50.0),
                  _trade("2024-02-09", "2024-03-08", -80.0, ticker="B"),
                  _trade("2024-03-15", "2024-04-12", 60.0, ticker="C")]
        acct = portfolio_sim.simulate_account(trades, stake=1000.0)
        self.assertAlmostEqual(acct["worst_drawdown"], -800.0, delta=1.0)


class BenchmarkTest(unittest.TestCase):
    def _bars(self):
        return [{"date": "2024-01-05", "close": 100.0},
                {"date": "2025-01-03", "close": 120.0},
                {"date": "2026-01-02", "close": 150.0}]

    def test_buy_and_hold_is_first_close_to_last(self):
        bm = portfolio_sim.benchmark_buy_and_hold(self._bars(), "2024-01-01", "2026-12-31")
        self.assertAlmostEqual(bm["total_return_pct"], 50.0)

    def test_the_window_actually_restricts_the_bars(self):
        bm = portfolio_sim.benchmark_buy_and_hold(self._bars(), "2024-01-01", "2025-06-30")
        self.assertAlmostEqual(bm["total_return_pct"], 20.0)

    def test_too_few_bars_in_window_returns_none(self):
        self.assertIsNone(
            portfolio_sim.benchmark_buy_and_hold(self._bars(), "2030-01-01", "2030-12-31"))


class ReportTest(unittest.TestCase):
    def test_a_losing_strategy_says_so_against_the_benchmark(self):
        """The finding I most need the report not to bury."""
        trades = [_trade("2024-01-05", "2025-01-03", 2.0)]
        bm = {"total_return_pct": 30.0, "cagr_pct": 30.0, "years": 1.0,
              "start": "2024-01-05", "end": "2025-01-03"}
        text = portfolio_sim.format_report(trades, benchmark=bm)
        self.assertIn("LOSES TO", text)

    def test_a_winning_strategy_is_not_labelled_a_loss(self):
        trades = [_trade("2024-01-05", "2025-01-03", 80.0)]
        bm = {"total_return_pct": 10.0, "cagr_pct": 10.0, "years": 1.0,
              "start": "2024-01-05", "end": "2025-01-03"}
        text = portfolio_sim.format_report(trades, benchmark=bm)
        self.assertIn("BEATS", text)
        self.assertNotIn("LOSES TO", text)


if __name__ == "__main__":
    unittest.main()


class CompoundingTest(unittest.TestCase):
    """Comparing a fixed-stake strategy against an index is rigged unless
    the strategy's profits are also put back to work — the index
    compounds whether or not the simulation does."""

    def test_compounding_beats_a_fixed_stake_when_trades_win(self):
        trades = [_trade("2024-01-05", "2024-06-07", 50.0),
                  _trade("2024-07-05", "2024-12-06", 50.0),
                  _trade("2025-01-10", "2025-06-06", 50.0)]
        flat = portfolio_sim.simulate_account(trades, stake=1000.0)
        comp = portfolio_sim.simulate_compounded(trades, stake=1000.0)
        self.assertGreater(comp["total_return_pct"], flat["total_return_pct"])

    def test_one_slot_compounds_multiplicatively(self):
        """Sequential trades never overlap, so there's one slot: $1,000
        through +100% twice is $4,000, not $3,000."""
        trades = [_trade("2024-01-05", "2024-06-07", 100.0),
                  _trade("2024-07-05", "2024-12-06", 100.0)]
        comp = portfolio_sim.simulate_compounded(trades, stake=1000.0)
        self.assertAlmostEqual(comp["starting_capital"], 1000.0)
        self.assertAlmostEqual(comp["ending_equity"], 4000.0, delta=1.0)

    def test_losses_compound_downward_too(self):
        trades = [_trade("2024-01-05", "2024-06-07", -50.0),
                  _trade("2024-07-05", "2024-12-06", -50.0)]
        comp = portfolio_sim.simulate_compounded(trades, stake=1000.0)
        self.assertAlmostEqual(comp["ending_equity"], 250.0, delta=1.0)
        self.assertLess(comp["cagr_pct"], 0)

    def test_drawdown_is_reported_as_a_percentage_of_the_high(self):
        """Up 100%, then halved: the fall is 50% from the peak even
        though the account is back where it started."""
        trades = [_trade("2024-01-05", "2024-06-07", 100.0),
                  _trade("2024-07-05", "2024-12-06", -50.0)]
        comp = portfolio_sim.simulate_compounded(trades, stake=1000.0)
        self.assertAlmostEqual(comp["worst_drawdown_pct"], -50.0, delta=1.0)

    def test_the_report_shows_the_compounded_line(self):
        trades = [_trade("2024-01-05", "2025-01-03", 20.0)]
        text = portfolio_sim.format_report(trades)
        self.assertIn("With profits reinvested", text)


class UncertaintyTest(unittest.TestCase):
    """"What's my return over 100 trades" is a range, not a number, and
    the range is usually wider than the average implies."""

    def _noisy(self):
        # Alternating big wins and losses: a real average near zero with
        # enough spread that 100 draws land all over the place.
        return [_trade("2024-01-05", "2024-06-07", pct)
                for pct in ([40.0, -30.0] * 60)]

    def test_percentiles_are_ordered(self):
        s = portfolio_sim.roi_uncertainty(self._noisy(), sample_size=100, draws=500)
        self.assertLessEqual(s["p5"], s["median"])
        self.assertLessEqual(s["median"], s["p95"])

    def test_a_noisy_strategy_produces_a_range_crossing_zero(self):
        s = portfolio_sim.roi_uncertainty(self._noisy(), sample_size=100, draws=500)
        self.assertLess(s["p5"], 0)
        self.assertGreater(s["p95"], 0)

    def test_a_uniformly_winning_strategy_never_loses_in_resampling(self):
        trades = [_trade("2024-01-05", "2024-06-07", 10.0) for _ in range(50)]
        s = portfolio_sim.roi_uncertainty(trades, sample_size=100, draws=200)
        self.assertAlmostEqual(s["median"], 10.0, delta=0.01)
        self.assertEqual(s["share_losing"], 0.0)

    def test_it_is_reproducible(self):
        a = portfolio_sim.roi_uncertainty(self._noisy(), draws=200)
        b = portfolio_sim.roi_uncertainty(self._noisy(), draws=200)
        self.assertEqual(a["median"], b["median"])

    def test_too_few_trades_returns_none(self):
        self.assertIsNone(portfolio_sim.roi_uncertainty([]))


class WipeoutCagrTest(unittest.TestCase):
    """Losses can exceed the capital base. Python's ** returns a complex
    number for a fractional power of a negative rather than raising, so
    an arm that lost more than it started with reported a CAGR of
    "-1.89+26.38j%" — which formats cleanly and means nothing."""

    def test_a_wiped_out_account_reports_minus_one_hundred_percent(self):
        trades = [_trade("2024-01-05", "2025-01-03", -150.0)]
        acct = portfolio_sim.simulate_account(trades, stake=1000.0)
        self.assertIsInstance(acct["cagr_pct"], float)
        self.assertAlmostEqual(acct["cagr_pct"], -100.0)

    def test_no_reported_rate_is_ever_complex(self):
        for pct in (-500.0, -150.0, -100.0, -99.0, 0.0, 250.0):
            acct = portfolio_sim.simulate_account(
                [_trade("2024-01-05", "2025-01-03", pct)], stake=1000.0)
            for key in ("cagr_pct", "cagr_on_average_pct"):
                self.assertIsInstance(acct[key], float,
                                      f"{key} went complex at {pct}%")

    def test_the_compounded_view_is_guarded_too(self):
        comp = portfolio_sim.simulate_compounded(
            [_trade("2024-01-05", "2025-01-03", -150.0)], stake=1000.0)
        self.assertIsInstance(comp["cagr_pct"], float)
        self.assertAlmostEqual(comp["cagr_pct"], -100.0)

    def test_ordinary_results_are_unaffected(self):
        acct = portfolio_sim.simulate_account(
            [_trade("2024-01-05", "2025-01-03", 100.0)], stake=1000.0)
        self.assertAlmostEqual(acct["cagr_pct"], 100.0, delta=1.0)
