"""Regressions for the reporting layer.

These test what the report *selects*, not how it looks. Formatting can
change freely; what mustn't change is which names land in which bucket,
because that's the part I'd act on. The diff report in particular has a
failure mode worth guarding: silently reporting a stage change as a
market event when it's really an artifact of comparing two scans that
covered different amounts of the market.
"""
import contextlib
import io
import os
import tempfile
import unittest

from screener import db, report


def _row(ticker, run_date, stage=2, met=8, price=50.0, actionable=True,
         sector="Banking Services", extended=False, percentile=90.0):
    return {
        "ticker": ticker,
        "run_date": run_date,
        "stage": stage,
        "price": price,
        "ma_30w": price * 0.94,
        "sector": sector,
        "conditions_met": met,
        "conditions_detail": {
            "stage_setup": {"result": True},
            "price_above_ma": {"result": True},
            "volume_confirmation": {"result": True, "volume_ratio": 2.4, "phase": "breakout"},
            "rs_improving": {"result": True, "rs_ma_rising": True},
            "sector_strength": {"result": True, "sector_strength_percentile": percentile},
            "market_stage": {"result": True},
            "resistance_breakout": {"result": None, "low_confidence": True},
            "pullback_quality": {"result": True},
            "risk_reward": {"result": met >= 8, "stop_pct": 12.0},
            "base": {"breakout_age_weeks": 3, "base_range_pct": 18.0, "base_is_tight": True},
            "stop_loss": {"recommended": price * 0.88, "method": "ma"},
            "entry_plan": {"extended": extended, "extended_pct": 20.0 if extended else -2.0,
                           "entries": [{"price": price, "size_pct": 100, "note": "n"}]},
            "scoring": {"actionable": actionable, "reason": "test row", "met": met,
                        "failed": 9 - met, "unknown": 0, "resolved": 9,
                        "required": 7, "score": met / 9, "blocking": []},
        },
    }


def _capture(fn, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(*args, **kwargs)
    return code, buf.getvalue()


class _TempDB(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._prev_path = db.DB_PATH
        db.DB_PATH = os.path.join(self._dir.name, "data", "test.db")
        db._schema_ready_for = None

    def tearDown(self):
        db.DB_PATH = self._prev_path
        db._schema_ready_for = None
        self._dir.cleanup()


class RunListingTest(_TempDB):
    def test_run_dates_come_back_newest_first(self):
        for d in ("2026-07-01", "2026-07-15", "2026-07-08"):
            db.insert_result(_row("AAA", d))
        self.assertEqual(db.get_run_dates(), ["2026-07-15", "2026-07-08", "2026-07-01"])

    def test_results_for_run_are_scoped_to_that_date(self):
        db.insert_result(_row("AAA", "2026-07-01"))
        db.insert_result(_row("BBB", "2026-07-01"))
        db.insert_result(_row("CCC", "2026-07-08"))
        self.assertEqual([r["ticker"] for r in db.get_results_for_run("2026-07-01")],
                         ["AAA", "BBB"])


class TickerReportTest(_TempDB):
    def test_unknown_ticker_reports_rather_than_raising(self):
        code, out = _capture(report.show_ticker, "NOPE")
        self.assertEqual(code, 1)
        self.assertIn("No stored results", out)

    def test_report_shows_the_verdict_and_every_condition(self):
        db.insert_result(_row("AAA", "2026-07-01", met=8))
        code, out = _capture(report.show_ticker, "AAA")
        self.assertEqual(code, 0)
        self.assertIn("ACTIONABLE", out)
        for _, label in report.CONDITION_LABELS:
            self.assertIn(label, out)

    def test_unresolved_conditions_are_not_shown_as_passing(self):
        """A '?' rendered as a pass would silently inflate the checklist."""
        db.insert_result(_row("AAA", "2026-07-01"))
        _, out = _capture(report.show_ticker, "AAA")
        line = next(l for l in out.splitlines() if "Resistance broken" in l)
        self.assertIn(report.MARKS[None].strip(), line)
        self.assertNotIn("PASS", line)

    def test_lookup_is_case_insensitive(self):
        db.insert_result(_row("AAA", "2026-07-01"))
        code, _ = _capture(report.show_ticker, "aaa")
        self.assertEqual(code, 0)


class DiffTest(_TempDB):
    def _two_scans(self):
        db.insert_result(_row("MOVER", "2026-07-01", stage=1, met=5, actionable=False))
        db.insert_result(_row("STAYER", "2026-07-01", stage=2, met=8, actionable=True))
        db.insert_result(_row("FADER", "2026-07-01", stage=2, met=8, actionable=True))
        db.insert_result(_row("MOVER", "2026-07-08", stage=2, met=8, actionable=True))
        db.insert_result(_row("STAYER", "2026-07-08", stage=2, met=8, actionable=True))
        db.insert_result(_row("FADER", "2026-07-08", stage=3, met=5, actionable=False))

    def test_needs_two_scans(self):
        db.insert_result(_row("AAA", "2026-07-01"))
        code, out = _capture(report.show_diff)
        self.assertEqual(code, 1)
        self.assertIn("Need two scans", out)

    def test_stage_one_to_two_is_identified_as_the_crossing(self):
        """The transition the whole method exists to catch."""
        self._two_scans()
        code, out = _capture(report.show_diff)
        self.assertEqual(code, 0)
        crossing = next(l for l in out.splitlines() if "the crossing" in l)
        self.assertIn("MOVER", crossing)
        self.assertIn("Stage 1 -> 2", crossing)

    def test_a_stage_2_to_3_move_is_reported_but_not_called_a_crossing(self):
        self._two_scans()
        _, out = _capture(report.show_diff)
        fader = next(l for l in out.splitlines() if l.strip().startswith("FADER"))
        self.assertIn("Stage 2 -> 3", fader)
        self.assertNotIn("the crossing", fader)

    def test_actionable_transitions_are_split_by_direction(self):
        self._two_scans()
        _, out = _capture(report.show_diff)
        new_block = out.split("Newly actionable")[1].split("No longer actionable")[0]
        lost_block = out.split("No longer actionable")[1]
        self.assertIn("MOVER", new_block)
        self.assertNotIn("FADER", new_block)
        self.assertIn("FADER", lost_block)

    def test_a_name_present_in_both_scans_is_never_reported_as_arriving(self):
        self._two_scans()
        _, out = _capture(report.show_diff)
        arrivals = out.split("Entered the scan:")[1]
        self.assertNotIn("STAYER", arrivals)

    def test_explicit_dates_override_the_default_pair(self):
        self._two_scans()
        db.insert_result(_row("MOVER", "2026-07-15", stage=2, met=9))
        _, out = _capture(report.show_diff, "2026-07-01", "2026-07-08")
        self.assertIn("2026-07-01  ->  2026-07-08", out)


class ActionableTest(_TempDB):
    def test_only_actionable_names_appear_by_default(self):
        db.insert_result(_row("GOOD", "2026-07-01", actionable=True))
        db.insert_result(_row("MEH", "2026-07-01", met=5, actionable=False))
        code, out = _capture(report.show_actionable)
        self.assertEqual(code, 0)
        self.assertIn("GOOD", out)
        self.assertNotIn("MEH", out)

    def test_min_met_widens_the_net_past_the_actionable_flag(self):
        db.insert_result(_row("MEH", "2026-07-01", met=6, actionable=False))
        _, out = _capture(report.show_actionable, min_met=6)
        self.assertIn("MEH", out)

    def test_exclude_extended_drops_names_past_the_entry_zone(self):
        db.insert_result(_row("INZONE", "2026-07-01", extended=False))
        db.insert_result(_row("CHASED", "2026-07-01", extended=True))
        _, out = _capture(report.show_actionable, include_extended=False)
        self.assertIn("INZONE", out)
        self.assertNotIn("CHASED", out)

    def test_an_empty_shortlist_is_reported_as_a_real_answer(self):
        db.insert_result(_row("MEH", "2026-07-01", met=4, actionable=False))
        code, out = _capture(report.show_actionable)
        self.assertEqual(code, 0)
        self.assertIn("Nothing qualifies", out)

    def test_stronger_sectors_are_listed_first(self):
        db.insert_result(_row("WEAK", "2026-07-01", sector="Weak Sector", percentile=20.0))
        db.insert_result(_row("STRONG", "2026-07-01", sector="Strong Sector", percentile=95.0))
        _, out = _capture(report.show_actionable)
        self.assertLess(out.index("Strong Sector"), out.index("Weak Sector"))

    def test_only_the_most_recent_scan_is_shown(self):
        db.insert_result(_row("OLD", "2026-07-01"))
        db.insert_result(_row("NEW", "2026-07-08"))
        _, out = _capture(report.show_actionable)
        self.assertIn("NEW", out)
        self.assertNotIn("OLD", out)


if __name__ == "__main__":
    unittest.main()


class CompareArmsTest(unittest.TestCase):
    """Scoring stored backtest arms.

    In the tool rather than a scratch script because the scratch
    directory was cleared between sessions on 2026-08-03, taking every
    analysis script with it. Anything worth running twice belongs in the
    repository.
    """

    def test_the_arms_flag_is_accepted(self):
        args = report._parse_args(["--arms", "b19_%"])
        self.assertEqual(args.arms, "b19_%")

    def test_a_cash_yield_can_be_supplied(self):
        args = report._parse_args(["--arms", "b19_%", "--cash-yield", "4.0"])
        self.assertAlmostEqual(args.cash_yield, 4.0)

    def test_cash_yield_defaults_to_zero(self):
        # The conservative reading has to be the default, so an assist
        # is always an explicit choice.
        self.assertEqual(report._parse_args(["--arms", "x"]).cash_yield, 0.0)

    def test_arms_is_mutually_exclusive_with_the_other_modes(self):
        with self.assertRaises(SystemExit):
            report._parse_args(["--arms", "x", "--runs"])
