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


class DistributionReportingTest(unittest.TestCase):
    """Means alone misrepresent a high-variance strategy.

    The best rule found in this project has a *worse* median trade than
    the baseline and a mean four times better, because its entire edge
    sits in the right tail. A reader given only the mean pictures a
    different strategy from the one that exists.
    """

    def _skewed(self):
        # Mostly small losses, occasional large wins — the shape that
        # makes a mean misleading.
        return ([_trade("2024-01-05", "2024-06-07", -8.0) for _ in range(70)]
                + [_trade("2024-01-05", "2024-06-07", 120.0) for _ in range(30)])

    def test_percentiles_land_on_the_right_values(self):
        """Asserted against a known distribution rather than only checking
        the ordering. Ordering alone passes when every percentile returns
        the minimum — a mutation doing exactly that survived."""
        # 0,1,2,...,99 — so the nth percentile is n.
        trades = [_trade("2024-01-05", "2024-06-07", float(i)) for i in range(100)]
        s = portfolio_sim.summarise_trades(trades)
        self.assertAlmostEqual(s["p5_pct"], 5.0, delta=1.0)
        self.assertAlmostEqual(s["p25_pct"], 25.0, delta=1.0)
        self.assertAlmostEqual(s["p75_pct"], 75.0, delta=1.0)
        self.assertAlmostEqual(s["p95_pct"], 95.0, delta=1.0)

    def test_percentiles_are_strictly_spread_on_a_varied_sample(self):
        trades = [_trade("2024-01-05", "2024-06-07", float(i)) for i in range(100)]
        s = portfolio_sim.summarise_trades(trades)
        self.assertLess(s["p5_pct"], s["p25_pct"])
        self.assertLess(s["p25_pct"], s["p75_pct"])
        self.assertLess(s["p75_pct"], s["p95_pct"])

    def test_a_negative_median_can_accompany_a_positive_mean(self):
        s = portfolio_sim.summarise_trades(self._skewed())
        self.assertLess(s["median_pct"], 0)
        self.assertGreater(s["mean_pct"], 0)

    def test_tail_shares_are_counted(self):
        """Both tails need trades in them. Asserting the losing share is
        zero on a fixture with no deep losses tests nothing — a mutation
        hard-coding it to zero survived that."""
        trades = ([_trade("2024-01-05", "2024-06-07", -35.0) for _ in range(20)]
                  + [_trade("2024-01-05", "2024-06-07", -5.0) for _ in range(50)]
                  + [_trade("2024-01-05", "2024-06-07", 120.0) for _ in range(30)])
        s = portfolio_sim.summarise_trades(trades)
        self.assertAlmostEqual(s["share_losing_20pct"], 20.0, delta=0.1)
        self.assertAlmostEqual(s["share_gaining_50pct"], 30.0, delta=0.1)

    def test_the_report_shows_the_spread(self):
        text = portfolio_sim.format_report(self._skewed())
        self.assertIn("The spread, which the average hides", text)
        self.assertIn("best 5%", text)


class PayoffGuardTest(unittest.TestCase):
    """A trade returning exactly 0% counts as a loss, so a sample whose
    only non-winners are flat makes the average loss zero and the payoff
    ratio divide by zero. Found by a percentile test using returns 0..99,
    where 0.0 was the sole 'loss'."""

    def test_a_flat_only_loss_set_does_not_raise(self):
        trades = ([_trade("2024-01-05", "2024-06-07", 0.0)]
                  + [_trade("2024-01-05", "2024-06-07", 10.0) for _ in range(5)])
        s = portfolio_sim.summarise_trades(trades)
        self.assertNotEqual(s["payoff"], s["payoff"])   # NaN

    def test_an_ordinary_payoff_still_computes(self):
        trades = ([_trade("2024-01-05", "2024-06-07", -10.0) for _ in range(2)]
                  + [_trade("2024-01-05", "2024-06-07", 20.0) for _ in range(2)])
        self.assertAlmostEqual(portfolio_sim.summarise_trades(trades)["payoff"], 2.0)


class FixedCapitalTest(unittest.TestCase):
    """The account that runs out of money. simulate_account() reports
    against peak capital (harsh, sizes for the worst week of a decade)
    and average capital (unachievable). Neither is what happens to a
    real account, and the gap between them has been the largest
    unresolved ambiguity in every result recorded so far.
    """

    def test_ample_capital_takes_every_signal(self):
        trades = [_trade("2020-01-01", "2020-06-01", 10.0, "AAA"),
                  _trade("2020-02-01", "2020-07-01", 20.0, "BBB")]
        acct = portfolio_sim.simulate_fixed_capital(trades, capital=10000.0, stake=1000.0)
        self.assertEqual(acct["skipped"], 0)
        self.assertEqual(acct["taken"], 2)
        # $10,000 start, two $1,000 stakes returning +10% and +20%.
        self.assertAlmostEqual(acct["ending_equity"], 10300.0)

    def test_running_out_of_money_skips_signals(self):
        trades = [_trade("2020-01-01", "2025-01-01", 10.0, "AAA"),
                  _trade("2020-01-02", "2025-01-01", 10.0, "BBB"),
                  _trade("2020-01-03", "2025-01-01", 10.0, "CCC")]
        acct = portfolio_sim.simulate_fixed_capital(trades, capital=2000.0, stake=1000.0)
        self.assertEqual(acct["taken"], 2)
        self.assertEqual(acct["skipped"], 1)

    def test_a_skipped_signal_earns_nothing(self):
        # The skipped trade is the profitable one. If its return leaks
        # into the total, the account was never really constrained.
        trades = [_trade("2020-01-01", "2025-01-01", 0.0, "AAA"),
                  _trade("2020-01-02", "2025-01-01", 500.0, "ZZZ")]
        acct = portfolio_sim.simulate_fixed_capital(trades, capital=1000.0, stake=1000.0)
        self.assertEqual(acct["taken"], 1)
        self.assertAlmostEqual(acct["ending_equity"], 1000.0)

    def test_a_skipped_signal_earns_nothing_when_it_closes_mid_run(self):
        # The same claim, but with the skipped trade closing *before* a
        # later entry, so it is drained by the in-loop exit handler
        # rather than the final one. The two paths are separate code and
        # the first version of this test only covered the final drain —
        # letting a skipped position pay out mid-run went unnoticed.
        trades = [_trade("2020-01-01", "2026-01-01", 0.0, "AAA"),
                  _trade("2020-01-02", "2020-03-01", 500.0, "ZZZ"),
                  _trade("2020-06-01", "2020-07-01", 0.0, "MMM")]
        acct = portfolio_sim.simulate_fixed_capital(trades, capital=1000.0, stake=1000.0)
        # AAA holds the only stake until 2026, so both later signals are
        # missed — including the one that would have returned 500%. That
        # is the whole point of the exercise: a fixed account's return is
        # decided as much by what it could not afford as by what it held.
        self.assertEqual(acct["taken"], 1)
        self.assertEqual(acct["skipped"], 2)
        self.assertAlmostEqual(acct["ending_equity"], 1000.0)

    def test_cash_freed_by_a_sale_funds_the_next_buy(self):
        # One position at a time, three signals in sequence. All three
        # should be funded because each closes before the next opens.
        trades = [_trade("2020-01-01", "2020-02-01", 10.0, "AAA"),
                  _trade("2020-03-01", "2020-04-01", 10.0, "BBB"),
                  _trade("2020-05-01", "2020-06-01", 10.0, "CCC")]
        acct = portfolio_sim.simulate_fixed_capital(trades, capital=1000.0, stake=1000.0)
        self.assertEqual(acct["taken"], 3)
        self.assertEqual(acct["peak_positions"], 1)

    def test_the_tie_break_is_arbitrary_and_the_seed_exposes_it(self):
        # Two signals the same day, money for one. Which gets funded is
        # decided by an arbitrary ordering, so the seed must be able to
        # change the answer — otherwise the sensitivity check that this
        # parameter exists to support is silently inert.
        trades = [_trade("2020-01-01", "2025-01-01", 0.0, "AAA"),
                  _trade("2020-01-01", "2025-01-01", 100.0, "BBB")]
        outcomes = {portfolio_sim.simulate_fixed_capital(
            trades, capital=1000.0, stake=1000.0, seed=s)["ending_equity"]
            for s in range(12)}
        self.assertGreater(len(outcomes), 1)

    def test_the_run_does_not_mutate_the_caller_s_trades(self):
        # Funding is tracked on the trade dicts, which are the caller's
        # objects. Leaving that bookkeeping behind would corrupt any
        # later run over the same list.
        trades = [_trade("2020-01-01", "2025-01-01", 10.0, "AAA")]
        portfolio_sim.simulate_fixed_capital(trades, capital=1000.0, stake=1000.0)
        self.assertNotIn("_funded", trades[0])

    def test_repeated_runs_agree(self):
        trades = [_trade("2020-01-01", "2021-01-01", 10.0, "AAA"),
                  _trade("2020-01-01", "2021-01-01", -5.0, "BBB"),
                  _trade("2020-06-01", "2021-06-01", 30.0, "CCC")]
        first = portfolio_sim.simulate_fixed_capital(trades, capital=2000.0)
        second = portfolio_sim.simulate_fixed_capital(trades, capital=2000.0)
        self.assertEqual(first["ending_equity"], second["ending_equity"])
        self.assertEqual(first["taken"], second["taken"])

    def test_idle_cash_earns_the_yield(self):
        # One $1,000 position for a year out of a $10,000 account at 4%.
        # $9,000 sits idle and should earn about $360.
        trades = [_trade("2020-01-01", "2021-01-01", 0.0, "AAA")]
        acct = portfolio_sim.simulate_fixed_capital(
            trades, capital=10000.0, stake=1000.0, cash_yield_pct=4.0)
        self.assertAlmostEqual(acct["interest_earned"], 360.0, delta=5.0)

    def test_cash_yield_is_off_by_default(self):
        trades = [_trade("2020-01-01", "2021-01-01", 0.0, "AAA")]
        acct = portfolio_sim.simulate_fixed_capital(trades, capital=10000.0)
        self.assertEqual(acct["interest_earned"], 0.0)
        self.assertAlmostEqual(acct["ending_equity"], 10000.0)

    def test_interest_does_not_accrue_on_money_in_a_position(self):
        # Same account, but fully deployed. Nothing is idle, so nothing
        # is earned — this fails if the yield is applied to total equity
        # rather than to the cash balance.
        trades = [_trade("2020-01-01", "2021-01-01", 0.0, "AAA")]
        acct = portfolio_sim.simulate_fixed_capital(
            trades, capital=1000.0, stake=1000.0, cash_yield_pct=4.0)
        self.assertAlmostEqual(acct["interest_earned"], 0.0, delta=0.01)

    def test_deployment_reports_how_much_money_was_working(self):
        # $1,000 of a $4,000 account, deployed the whole time: 25%.
        trades = [_trade("2020-01-01", "2021-01-01", 0.0, "AAA")]
        acct = portfolio_sim.simulate_fixed_capital(
            trades, capital=4000.0, stake=1000.0)
        self.assertAlmostEqual(acct["deployed_vs_start_pct"], 25.0, delta=0.5)

    def test_interest_reaches_the_ending_balance(self):
        # Reporting the interest but never crediting it leaves every
        # figure that matters unchanged, which is exactly the kind of
        # error that reads as correct.
        trades = [_trade("2020-01-01", "2021-01-01", 0.0, "AAA")]
        acct = portfolio_sim.simulate_fixed_capital(
            trades, capital=10000.0, stake=1000.0, cash_yield_pct=4.0)
        self.assertAlmostEqual(acct["ending_equity"], 10360.0, delta=5.0)
        self.assertGreater(acct["cagr_pct"], 3.0)

    def test_a_sale_funds_a_purchase_made_the_same_day(self):
        # Exits must be settled before entries on a shared date. With
        # the ordering reversed the second signal is missed for want of
        # money that was already there, and no test with non-overlapping
        # dates can tell the difference.
        trades = [_trade("2020-01-01", "2020-06-01", 0.0, "AAA"),
                  _trade("2020-06-01", "2020-12-01", 0.0, "BBB")]
        acct = portfolio_sim.simulate_fixed_capital(
            trades, capital=1000.0, stake=1000.0)
        self.assertEqual(acct["taken"], 2)
        self.assertEqual(acct["skipped"], 0)

    def test_priority_decides_which_competing_signal_is_funded(self):
        # Two signals, one stake. The better-ranked one must win
        # regardless of the alphabetical fallback, which would otherwise
        # pick AAA.
        trades = [_trade("2020-01-01", "2025-01-01", 0.0, "AAA"),
                  _trade("2020-01-01", "2025-01-01", 100.0, "ZZZ")]
        trades[0]["conditions_met"] = 4
        trades[1]["conditions_met"] = 6
        acct = portfolio_sim.simulate_fixed_capital(
            trades, capital=1000.0, stake=1000.0,
            priority=lambda t: t["conditions_met"])
        self.assertAlmostEqual(acct["ending_equity"], 2000.0)

    def test_priority_survives_the_seed_shuffle(self):
        # The shuffle exists to randomise arbitrary ties. If it reshuffles
        # across priority levels it silently cancels the ranking, and the
        # comparison the ranking was built for measures nothing.
        trades = [_trade("2020-01-01", "2025-01-01", 0.0, "AAA"),
                  _trade("2020-01-01", "2025-01-01", 100.0, "ZZZ")]
        trades[0]["conditions_met"] = 4
        trades[1]["conditions_met"] = 6
        equities = {portfolio_sim.simulate_fixed_capital(
            trades, capital=1000.0, stake=1000.0, seed=s,
            priority=lambda t: t["conditions_met"])["ending_equity"]
            for s in range(15)}
        self.assertEqual(equities, {2000.0})

    def test_the_seed_still_breaks_ties_within_a_priority_level(self):
        # Equal rank, so the ranking has nothing to say and the seed must
        # still be able to change the outcome.
        trades = [_trade("2020-01-01", "2025-01-01", 0.0, "AAA"),
                  _trade("2020-01-01", "2025-01-01", 100.0, "ZZZ")]
        trades[0]["conditions_met"] = 5
        trades[1]["conditions_met"] = 5
        equities = {portfolio_sim.simulate_fixed_capital(
            trades, capital=1000.0, stake=1000.0, seed=s,
            priority=lambda t: t["conditions_met"])["ending_equity"]
            for s in range(15)}
        self.assertGreater(len(equities), 1)


class MarkToMarketTest(unittest.TestCase):
    """Drawdown measured on open positions, not just closed ones.

    Carrying an open position at cost means an unrealised loss shows
    nothing until the trade closes, so worst_drawdown only ever sees
    damage already realised. Every defensive claim this project makes
    rests on drawdown, which made that the most important number in the
    codebase and the one measured wrong.
    """

    TRADE = [{"ticker": "AAA", "entry_date": "2020-01-01", "exit_date": "2020-06-01",
              "entry_price": 10.0, "return_pct": 0.0, "still_open": 0}]
    BARS = {"AAA": [{"time": "2020-01-01", "close": 10.0},
                    {"time": "2020-03-01", "close": 4.0},
                    {"time": "2020-06-01", "close": 10.0}]}

    def test_cost_basis_hides_an_unrealised_loss(self):
        # The behaviour being corrected. A position that halved and
        # recovered shows no drawdown at all.
        acct = portfolio_sim.simulate_fixed_capital(self.TRADE, capital=5000.0)
        self.assertFalse(acct["marked_to_market"])
        self.assertEqual(acct["worst_drawdown"], 0.0)

    def test_marking_to_market_reveals_it(self):
        # 100 shares at $10, down to $4: a $600 fall the account would
        # have watched happen.
        acct = portfolio_sim.simulate_fixed_capital(
            self.TRADE, capital=5000.0, bars_by_symbol=self.BARS)
        self.assertTrue(acct["marked_to_market"])
        self.assertAlmostEqual(acct["worst_drawdown"], -600.0, delta=1.0)

    def test_the_final_return_is_unchanged_either_way(self):
        # Marking changes the path, not the destination. If ending equity
        # moves, the valuation has leaked into realised profit.
        plain = portfolio_sim.simulate_fixed_capital(self.TRADE, capital=5000.0)
        marked = portfolio_sim.simulate_fixed_capital(
            self.TRADE, capital=5000.0, bars_by_symbol=self.BARS)
        self.assertAlmostEqual(plain["ending_equity"], marked["ending_equity"])
        self.assertAlmostEqual(plain["cagr_pct"], marked["cagr_pct"])

    def test_prices_after_the_mark_date_are_never_used(self):
        # A valuation that peeked forward would rate the position at $10
        # in March and report no drawdown — lookahead wearing the costume
        # of a fix.
        acct = portfolio_sim.simulate_fixed_capital(
            self.TRADE, capital=5000.0, bars_by_symbol=self.BARS)
        self.assertLess(acct["worst_drawdown"], -500.0)

    def test_a_symbol_with_no_prices_does_not_crash_the_valuation(self):
        acct = portfolio_sim.simulate_fixed_capital(
            self.TRADE, capital=5000.0, bars_by_symbol={"ZZZ": []})
        self.assertTrue(acct["marked_to_market"])

    def test_a_deeper_fall_produces_a_deeper_drawdown(self):
        # Monotonicity: the metric has to respond to severity, not merely
        # to the existence of a dip.
        shallow = dict(self.BARS)
        deep = {"AAA": [{"time": "2020-01-01", "close": 10.0},
                        {"time": "2020-03-01", "close": 2.0},
                        {"time": "2020-06-01", "close": 10.0}]}
        a = portfolio_sim.simulate_fixed_capital(
            self.TRADE, capital=5000.0, bars_by_symbol=shallow)["worst_drawdown"]
        b = portfolio_sim.simulate_fixed_capital(
            self.TRADE, capital=5000.0, bars_by_symbol=deep)["worst_drawdown"]
        self.assertLess(b, a)

    def test_the_price_lookup_itself_never_looks_forward(self):
        # Asserted on the helper directly. Going through the account
        # simulation could not distinguish a one-bar forward shift from
        # correct behaviour — the drawdown appeared either way, just at a
        # different mark — so the mutation survived a test of the outcome
        # and needed a test of the mechanism.
        index = portfolio_sim._price_index(self.BARS)
        self.assertEqual(portfolio_sim._price_as_of(index, "AAA", "2020-02-15"), 10.0,
                         "mid-February must see January's close, not March's")
        self.assertEqual(portfolio_sim._price_as_of(index, "AAA", "2020-03-01"), 4.0)
        self.assertEqual(portfolio_sim._price_as_of(index, "AAA", "2020-05-31"), 4.0,
                         "late May must see March's close, not June's")
        self.assertIsNone(portfolio_sim._price_as_of(index, "AAA", "2019-12-31"),
                          "before the series starts there is no price")

    def test_drawdown_percent_is_measured_against_the_peak_not_the_start(self):
        # An account that compounds and then falls must report the fall
        # relative to what it had, not to what it started with. Against
        # starting capital a real 45% fall can print as 113%, which is
        # impossible without leverage and was briefly reported as fact.
        trades = [{"ticker": "AAA", "entry_date": "2020-01-01",
                   "exit_date": "2020-02-01", "entry_price": 10.0,
                   "return_pct": 400.0, "still_open": 0},
                  {"ticker": "BBB", "entry_date": "2020-03-01",
                   "exit_date": "2020-04-01", "entry_price": 10.0,
                   "return_pct": -50.0, "still_open": 0}]
        acct = portfolio_sim.simulate_fixed_capital(trades, capital=1000.0, stake=1000.0)
        self.assertGreaterEqual(acct["worst_drawdown_pct"], -100.0)
        self.assertLessEqual(acct["worst_drawdown_pct"], 0.0)


class RiskBasedSizingTest(unittest.TestCase):
    """Position size set by risk, not by a flat dollar amount.

    A flat $1,000 into a trade stopping out at 5% risks $50; the same
    $1,000 into one stopping at 15% risks $150. The account was betting
    three times as much on the second without anyone choosing that.
    Sizing by risk holds the loss-if-wrong constant instead.
    """

    def _trade(self, ticker, ret, r_multiple, entry="2020-01-01", exit_="2020-06-01"):
        return {"ticker": ticker, "entry_date": entry, "exit_date": exit_,
                "entry_price": 100.0, "return_pct": ret, "r_multiple": r_multiple,
                "still_open": 0}

    def test_implied_stop_is_recovered_from_the_r_multiple(self):
        # +20% at 2R means the risk was 10% of entry.
        self.assertAlmostEqual(
            portfolio_sim.implied_stop_pct(self._trade("A", 20.0, 2.0)), 10.0)

    def test_a_missing_r_multiple_gives_no_stop_distance(self):
        self.assertIsNone(portfolio_sim.implied_stop_pct(self._trade("A", 20.0, None)))
        self.assertIsNone(portfolio_sim.implied_stop_pct(self._trade("A", 20.0, 0.0)))

    def test_a_tighter_stop_earns_a_larger_position(self):
        # Same account, same risk budget: a 5% stop should take roughly
        # three times the position of a 15% stop.
        tight = portfolio_sim._stake_for(self._trade("A", 10.0, 2.0),   # 5% stop
                                         100000.0, 1000.0, 1.0, 1e9)
        wide = portfolio_sim._stake_for(self._trade("B", 15.0, 1.0),    # 15% stop
                                        100000.0, 1000.0, 1.0, 1e9)
        self.assertAlmostEqual(tight / wide, 3.0, places=6)

    def test_the_risk_budget_is_what_is_held_constant(self):
        # 1% of $100,000 is $1,000 of risk. A 5% stop therefore buys
        # $20,000 of stock, because 5% of $20,000 is $1,000.
        stake = portfolio_sim._stake_for(self._trade("A", 10.0, 2.0),
                                         100000.0, 1000.0, 1.0, 1e9)
        self.assertAlmostEqual(stake, 20000.0, places=6)

    def test_no_single_position_exceeds_the_cap(self):
        # A very tight stop would otherwise demand an absurd position.
        stake = portfolio_sim._stake_for(self._trade("A", 100.0, 200.0),
                                         100000.0, 1000.0, 1.0, 10000.0)
        self.assertLessEqual(stake, 10000.0)

    def test_an_unknown_stop_falls_back_to_the_flat_stake(self):
        # The conservative direction: unknown risk must not be rewarded
        # with an outsized position.
        stake = portfolio_sim._stake_for(self._trade("A", 10.0, None),
                                         100000.0, 1000.0, 1.0, 1e9)
        self.assertEqual(stake, 1000.0)

    def test_sizing_off_reproduces_the_flat_stake_result(self):
        trades = [self._trade("A", 10.0, 2.0), self._trade("B", -5.0, -1.0)]
        flat = portfolio_sim.simulate_fixed_capital(trades, capital=50000.0)
        self.assertAlmostEqual(flat["ending_equity"], 50000.0 + 100.0 - 50.0, places=6)

    def test_sizing_on_changes_the_outcome(self):
        # If risk_pct were ignored, both runs would be identical — the
        # failure mode that made an earlier experiment run its control
        # twice and report a real change as inert.
        trades = [self._trade("A", 10.0, 2.0), self._trade("B", -5.0, -1.0)]
        flat = portfolio_sim.simulate_fixed_capital(trades, capital=50000.0)
        risked = portfolio_sim.simulate_fixed_capital(
            trades, capital=50000.0, risk_pct=1.0)
        self.assertNotAlmostEqual(flat["ending_equity"], risked["ending_equity"])

    def test_the_committed_stake_is_what_gets_returned_at_exit(self):
        # Exiting on the flat stake while having funded a larger one
        # would manufacture or destroy money silently.
        #
        # The return has to be non-zero: a 0% trade makes the implied
        # stop undefined, so sizing falls back to the flat stake and the
        # test exercises nothing. My first version did exactly that and
        # let two mutations through.
        #
        # +10% at 2R is a 5% stop. Risking 1% of $100,000 wants $20,000,
        # capped at a tenth of the book, so $10,000 goes in and $11,000
        # comes back.
        trades = [self._trade("A", 10.0, 2.0)]
        acct = portfolio_sim.simulate_fixed_capital(
            trades, capital=100000.0, risk_pct=1.0)
        self.assertAlmostEqual(acct["ending_equity"], 101000.0, places=2)

    def test_the_stop_distance_is_a_magnitude_not_a_signed_number(self):
        # A losing trade carries a negative return and a negative
        # r_multiple, so the ratio comes out positive on its own. The
        # guard matters when the two disagree in sign, which would
        # otherwise yield a negative "distance" and an absurd position.
        self.assertAlmostEqual(
            portfolio_sim.implied_stop_pct(self._trade("A", -10.0, 2.0)), 5.0)
        self.assertAlmostEqual(
            portfolio_sim.implied_stop_pct(self._trade("A", 10.0, -2.0)), 5.0)

    def test_bookkeeping_is_cleaned_off_the_caller_s_trades(self):
        trades = [self._trade("A", 10.0, 2.0)]
        portfolio_sim.simulate_fixed_capital(trades, capital=50000.0, risk_pct=1.0)
        self.assertNotIn("_stake", trades[0])
        self.assertNotIn("_funded", trades[0])
