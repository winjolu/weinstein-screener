"""Portfolio state, stop maintenance, and the recommendation log.

The log is the part worth testing hardest. It is the only forward
evidence this project will produce — everything in docs/ is a backtest
over history I have already read — so a bug that quietly drops rows or
overwrites outcomes would destroy the one record that cannot be tuned
after the fact.
"""
import os
import tempfile
import unittest

from screener import db, portfolio
from tests.synthetic import bar, weekly_dates


def _bars(closes, start="2024-01-05"):
    return [bar(d, c * 1.03, c * 0.97, c)
            for d, c in zip(weekly_dates(len(closes), start), closes)]


class PositionsTest(unittest.TestCase):
    def setUp(self):
        self.book = {"cash": 10000.0, "positions": []}

    def test_a_position_records_what_was_paid_and_where_the_stop_is(self):
        portfolio.add_position(self.book, "aapl", 100, 42.5, 38.0,
                               entry_date="2026-01-15")
        held = portfolio.position_for(self.book, "AAPL")
        self.assertEqual(held["shares"], 100)
        self.assertAlmostEqual(held["cost_basis"], 42.5)
        self.assertAlmostEqual(held["stop"], 38.0)

    def test_tickers_are_matched_case_insensitively(self):
        portfolio.add_position(self.book, "aapl", 10, 40.0, 36.0)
        self.assertIsNotNone(portfolio.position_for(self.book, "AAPL"))
        self.assertIsNotNone(portfolio.position_for(self.book, "aapl"))

    def test_buying_more_averages_the_cost_rather_than_adding_a_row(self):
        # Two rows for one holding would mean two stops on one position.
        portfolio.add_position(self.book, "AAA", 100, 40.0, 36.0)
        portfolio.add_position(self.book, "AAA", 100, 50.0, 44.0)
        self.assertEqual(len(self.book["positions"]), 1)
        held = portfolio.position_for(self.book, "AAA")
        self.assertEqual(held["shares"], 200)
        self.assertAlmostEqual(held["cost_basis"], 45.0)

    def test_adding_to_a_winner_never_loosens_the_existing_stop(self):
        portfolio.add_position(self.book, "AAA", 100, 40.0, 38.0)
        portfolio.add_position(self.book, "AAA", 100, 50.0, 35.0)
        self.assertAlmostEqual(portfolio.position_for(self.book, "AAA")["stop"], 38.0)

    def test_closing_returns_the_position_so_the_exit_can_be_logged(self):
        portfolio.add_position(self.book, "AAA", 100, 40.0, 36.0)
        closed = portfolio.close_position(self.book, "AAA")
        self.assertEqual(closed["ticker"], "AAA")
        self.assertEqual(self.book["positions"], [])

    def test_closing_something_not_held_is_not_an_error(self):
        self.assertIsNone(portfolio.close_position(self.book, "ZZZ"))


class PersistenceTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._dir.name, "config", "portfolio.json")

    def tearDown(self):
        self._dir.cleanup()

    def test_a_missing_file_is_an_empty_portfolio_not_a_crash(self):
        # A new user has no positions. That is a state, not a failure.
        book = portfolio.load(self.path)
        self.assertEqual(book["positions"], [])

    def test_a_saved_portfolio_round_trips(self):
        book = {"cash": 5000.0, "positions": []}
        portfolio.add_position(book, "AAA", 100, 40.0, 36.0)
        portfolio.save(book, self.path)
        self.assertEqual(portfolio.load(self.path)["positions"][0]["ticker"], "AAA")

    def test_no_partial_file_is_left_behind(self):
        book = {"cash": 1.0, "positions": []}
        portfolio.save(book, self.path)
        self.assertFalse(os.path.exists(self.path + ".partial"))


class TrailingStopTest(unittest.TestCase):
    def setUp(self):
        self.book = {"cash": 0.0, "positions": []}

    def test_a_stop_is_raised_as_the_position_advances(self):
        bars = _bars([50.0 + i for i in range(60)])
        portfolio.add_position(self.book, "AAA", 100, 50.0, 45.0,
                               entry_date=bars[0]["time"][:10])
        changes = portfolio.refresh_stops(self.book, {"AAA": bars})
        self.assertEqual(changes[0]["status"], "raised")
        self.assertGreater(portfolio.position_for(self.book, "AAA")["stop"], 45.0)

    def test_a_stop_never_falls(self):
        # The property that makes it protection rather than a slower way
        # of losing. A stop that can retreat is not a stop.
        bars = _bars([50.0 + i for i in range(40)] + [60.0 - i for i in range(20)])
        portfolio.add_position(self.book, "AAA", 100, 50.0, 999.0,
                               entry_date=bars[0]["time"][:10])
        before = portfolio.position_for(self.book, "AAA")["stop"]
        portfolio.refresh_stops(self.book, {"AAA": bars})
        self.assertEqual(portfolio.position_for(self.book, "AAA")["stop"], before)

    def test_a_symbol_with_no_bars_is_reported_not_skipped_silently(self):
        portfolio.add_position(self.book, "ZZZ", 10, 5.0, 4.0)
        changes = portfolio.refresh_stops(self.book, {})
        self.assertEqual(changes[0]["status"], "no data")

    def test_a_touched_stop_is_detected_on_the_low_not_the_close(self):
        # A stop is an order resting in the market. It fills when price
        # trades through it, not when the week happens to close below.
        bars = _bars([50.0] * 10)
        bars[-1]["low"] = 40.0
        bars[-1]["close"] = 50.0
        portfolio.add_position(self.book, "AAA", 100, 50.0, 45.0,
                               entry_date=bars[0]["time"][:10])
        hit = portfolio.stops_hit(self.book, {"AAA": bars})
        self.assertEqual(len(hit), 1)
        self.assertAlmostEqual(hit[0]["stop"], 45.0)

    def test_an_untouched_stop_is_not_reported(self):
        bars = _bars([50.0] * 10)
        portfolio.add_position(self.book, "AAA", 100, 50.0, 40.0,
                               entry_date=bars[0]["time"][:10])
        self.assertEqual(portfolio.stops_hit(self.book, {"AAA": bars}), [])


class RecommendationLogTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._prev = db.DB_PATH
        db.DB_PATH = os.path.join(self._dir.name, "data", "test.db")
        db._schema_ready_for = None

    def tearDown(self):
        db.DB_PATH = self._prev
        db._schema_ready_for = None
        self._dir.cleanup()

    def test_a_suggestion_is_recorded_before_the_outcome_is_known(self):
        portfolio.log_recommendation("AAA", "buy", suggested_on="2026-08-03",
                                     shares=100, price=42.5, stop=38.0,
                                     rationale="stage 2 breakout")
        rows = db.get_recommendations()
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["taken"])

    def test_what_was_actually_done_is_recorded_separately(self):
        portfolio.log_recommendation("AAA", "buy", suggested_on="2026-08-03",
                                     price=42.5)
        portfolio.record_outcome("AAA", "2026-08-03", True, "filled at 42.61")
        row = db.get_recommendations()[0]
        self.assertEqual(row["taken"], "True")
        self.assertIn("42.61", row["taken_note"])

    def test_a_partial_or_hedged_answer_survives_as_itself(self):
        # "bought half" and "waited a week" are the observations that
        # reveal whether suggestions are usable. Flattening them to a
        # boolean throws away the finding.
        portfolio.log_recommendation("AAA", "buy", suggested_on="2026-08-03")
        portfolio.record_outcome("AAA", "2026-08-03", "bought half")
        self.assertEqual(db.get_recommendations()[0]["taken"], "bought half")

    def test_suggestions_not_acted_on_are_kept(self):
        # A log of only the trades taken measures my judgement as
        # much as the system's. The gap between them is the point.
        portfolio.log_recommendation("AAA", "buy", suggested_on="2026-08-03")
        portfolio.record_outcome("AAA", "2026-08-03", False, "too extended")
        row = db.get_recommendations()[0]
        self.assertEqual(row["taken"], "False")
        self.assertEqual(row["taken_note"], "too extended")

    def test_rerunning_the_same_day_corrects_rather_than_duplicates(self):
        for price in (42.5, 43.0):
            portfolio.log_recommendation("AAA", "buy", suggested_on="2026-08-03",
                                         price=price)
        rows = db.get_recommendations()
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["price"], 43.0)

    def test_the_same_ticker_on_different_days_is_two_records(self):
        portfolio.log_recommendation("AAA", "buy", suggested_on="2026-08-03")
        portfolio.log_recommendation("AAA", "buy", suggested_on="2026-08-10")
        self.assertEqual(len(db.get_recommendations()), 2)

    def test_the_scoreboard_shows_how_a_suggestion_has_done_since(self):
        portfolio.log_recommendation("AAA", "buy", suggested_on="2026-08-03",
                                     price=100.0)
        board = portfolio.scoreboard({"AAA": _bars([100.0, 110.0])})
        self.assertAlmostEqual(board[0]["move_pct"], 10.0, places=6)
