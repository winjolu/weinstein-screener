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


class ReconcileBrokerOrdersTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._prev = db.DB_PATH
        db.DB_PATH = os.path.join(self._dir.name, "data", "test.db")
        db._schema_ready_for = None

    def tearDown(self):
        db.DB_PATH = self._prev
        db._schema_ready_for = None
        self._dir.cleanup()

    """Folding real broker order history into the forward log.

    The case this exists for: a stop-loss order sat live on an account
    for days, unmentioned, because nobody happened to describe it. This
    reads the broker's own record instead of relying on anyone to.
    """

    def _combo(self, symbol, side, order_type, status, qty, **extra):
        leg = {"symbol": symbol, "side": side, "order_type": order_type,
              "status": status, "total_quantity": str(qty),
              "filled_quantity": str(qty) if status == "FILLED" else "0",
              "time_in_force": "GTC"}
        leg.update(extra)
        return {"orders": [leg]}

    def test_a_filled_buy_becomes_a_buy_record(self):
        history = [self._combo("TMFC", "BUY", "LIMIT", "FILLED", 20,
                               filled_price="80.46", limit_price="80.50",
                               filled_time_at="2026-08-07T15:49:07.401Z")]
        n = portfolio.reconcile_broker_orders(history)
        self.assertEqual(n, 1)
        rows = db.get_recommendations("TMFC")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "buy")
        self.assertAlmostEqual(rows[0]["price"], 80.46)
        self.assertEqual(rows[0]["suggested_on"], "2026-08-07")

    def test_a_filled_sell_becomes_a_sell_record(self):
        history = [self._combo("PSEC", "SELL", "MARKET", "FILLED", 1,
                               filled_price="2.27",
                               filled_time_at="2026-08-10T15:24:06.017Z")]
        portfolio.reconcile_broker_orders(history)
        rows = db.get_recommendations("PSEC")
        self.assertEqual(rows[0]["action"], "sell")
        self.assertAlmostEqual(rows[0]["price"], 2.27)

    def test_a_working_stop_is_logged_even_though_it_has_not_filled(self):
        # The order that started this: a live stop is real account state
        # the moment it is placed, not only once it triggers.
        history = [self._combo("TMFC", "SELL", "STOP_LOSS", "SUBMITTED", 20,
                               stop_price="72.00",
                               place_time_at="2026-08-07T15:49:07.206Z")]
        portfolio.reconcile_broker_orders(history)
        rows = db.get_recommendations("TMFC")
        self.assertEqual(rows[0]["action"], "stop_set")
        self.assertAlmostEqual(rows[0]["stop"], 72.00)

    def test_a_stop_limit_records_both_prices_in_the_note(self):
        history = [self._combo("TEAM", "SELL", "STOP_LOSS_LIMIT", "SUBMITTED", 10,
                               stop_price="120.00", limit_price="115.00",
                               place_time_at="2026-08-10T15:04:57.180Z")]
        portfolio.reconcile_broker_orders(history)
        note = db.get_recommendations("TEAM")[0]["taken_note"]
        self.assertIn("120.00", note)
        self.assertIn("115.00", note)

    def test_the_stop_note_includes_time_in_force_and_quantity(self):
        # Stop and limit prices alone are not enough to act on later — a
        # stop with no recorded TIF looks identical to one that quietly
        # expired at the close, which is the exact trap a Day order sets.
        history = [self._combo("NVDA", "SELL", "STOP_LOSS", "SUBMITTED", 1,
                               stop_price="176.00",
                               place_time_at="2026-08-10T15:18:01.113Z")]
        portfolio.reconcile_broker_orders(history)
        note = db.get_recommendations("NVDA")[0]["taken_note"]
        self.assertIn("GTC", note)
        self.assertIn("qty 1", note)

    def test_a_working_stop_records_its_real_quantity_not_zero(self):
        # The bug this exists to catch: a broker reports filled_quantity
        # as the string "0" on an order that has not filled, and "0" or
        # total_quantity is truthy regardless of what the string says —
        # the fallback never triggers, and every stop reads as covering
        # no shares. Checked against the note text on a size a stray "1"
        # or "0" elsewhere in the string could not disguise.
        history = [self._combo("TMFC", "SELL", "STOP_LOSS", "SUBMITTED", 20,
                               stop_price="72.00",
                               place_time_at="2026-08-07T15:49:07.206Z")]
        portfolio.reconcile_broker_orders(history)
        note = db.get_recommendations("TMFC")[0]["taken_note"]
        self.assertIn("qty 20", note)
        self.assertNotIn("qty 0", note)

    def test_an_unfilled_ordinary_order_is_not_logged_as_a_trade(self):
        # A resting limit buy that has not filled is not a completed
        # event. Logging it as one would record a trade that never
        # happened.
        history = [self._combo("AAPL", "BUY", "LIMIT", "WORKING", 5,
                               place_time_at="2026-08-10T15:00:00.000Z")]
        n = portfolio.reconcile_broker_orders(history)
        self.assertEqual(n, 0)
        self.assertEqual(db.get_recommendations("AAPL"), [])

    def test_rerunning_the_same_history_does_not_duplicate(self):
        history = [self._combo("NVDA", "BUY", "LIMIT", "FILLED", 1,
                               filled_price="219.42",
                               filled_time_at="2026-08-10T15:18:01.172Z")]
        portfolio.reconcile_broker_orders(history)
        portfolio.reconcile_broker_orders(history)
        self.assertEqual(len(db.get_recommendations("NVDA")), 1)

    def test_a_leg_missing_a_symbol_is_skipped_rather_than_raising(self):
        history = [{"orders": [{"side": "BUY", "order_type": "MARKET",
                                "status": "FILLED", "total_quantity": "1"}]}]
        self.assertEqual(portfolio.reconcile_broker_orders(history), 0)

    def test_multiple_legs_across_combos_are_all_processed(self):
        # The real shape: a bracket order is a MASTER combo (the entry)
        # paired with a separate STOP_LOSS combo, not one leg on one
        # combo. Both have to be walked.
        history = [
            self._combo("NVDA", "BUY", "LIMIT", "FILLED", 1,
                       filled_price="219.42",
                       filled_time_at="2026-08-10T15:18:01.172Z"),
            self._combo("NVDA", "SELL", "STOP_LOSS", "SUBMITTED", 1,
                       stop_price="176.00",
                       place_time_at="2026-08-10T15:18:01.113Z"),
        ]
        n = portfolio.reconcile_broker_orders(history)
        self.assertEqual(n, 2)
        actions = {r["action"] for r in db.get_recommendations("NVDA")}
        self.assertEqual(actions, {"buy", "stop_set"})
