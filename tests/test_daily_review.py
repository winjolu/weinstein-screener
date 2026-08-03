"""The daily review.

Two properties are asserted hardest. First, that entries wait for the
weekly bar to close — acting midweek reads a number that does not exist
yet. Second, that every suggestion carries a share count and a stop:
output that cannot be checked against a chart or scored later against
what happened is not usable, however carefully hedged.
"""
import datetime
import unittest

from screener import daily_review, portfolio
from tests.synthetic import bar, weekly_dates


def _bars(closes, start="2024-01-05"):
    return [bar(d, c * 1.03, c * 0.97, c)
            for d, c in zip(weekly_dates(len(closes), start), closes)]


SATURDAY = datetime.date(2026, 8, 1)
WEDNESDAY = datetime.date(2026, 8, 5)


class TimingTest(unittest.TestCase):
    def test_the_weekly_bar_is_closed_at_the_weekend(self):
        self.assertTrue(daily_review._weekly_bar_is_closed(SATURDAY))
        self.assertTrue(daily_review._weekly_bar_is_closed(datetime.date(2026, 8, 2)))

    def test_it_is_not_closed_midweek(self):
        self.assertFalse(daily_review._weekly_bar_is_closed(WEDNESDAY))

    def test_no_purchases_are_suggested_midweek(self):
        # A breakout measured on a Wednesday sits on a bar with two days
        # left to change its mind.
        book = {"cash": 100000.0, "positions": []}
        candidates = [{"ticker": "AAA", "price": 100.0, "stop": 92.0}]
        result = daily_review.review(book, {}, candidates, today=WEDNESDAY)
        self.assertEqual(result["buys"], [])

    def test_purchases_are_suggested_at_the_weekend(self):
        book = {"cash": 100000.0, "positions": []}
        candidates = [{"ticker": "AAA", "price": 100.0, "stop": 92.0}]
        result = daily_review.review(book, {}, candidates, today=SATURDAY)
        self.assertEqual(len(result["buys"]), 1)

    def test_stops_are_still_maintained_midweek(self):
        # The weekday run has a real job: a stop is a price event and can
        # trigger any day.
        book = {"cash": 0.0, "positions": []}
        bars = _bars([50.0 + i for i in range(60)])
        portfolio.add_position(book, "AAA", 100, 50.0, 45.0,
                               entry_date=bars[0]["time"][:10])
        result = daily_review.review(book, {"AAA": bars}, today=WEDNESDAY)
        self.assertTrue(result["stops"])


class SizingTest(unittest.TestCase):
    def test_shares_come_from_the_distance_to_the_stop(self):
        # 1% of $100,000 is $1,000 at risk. A $15 gap between entry and
        # stop therefore buys 66 shares.
        #
        # The stop has to be wide enough that the position cap does not
        # bind, or this tests the cap instead of the sizing. Position
        # size is risk% / stop%, so at 1% risk any stop tighter than 10%
        # wants more than a tenth of the account and gets capped — which
        # is most real stops, and is asserted separately below.
        sized = daily_review._size(
            {"ticker": "AAA", "price": 100.0, "stop": 85.0}, 100000.0, 1.0)
        self.assertEqual(sized["shares"], 66)
        self.assertAlmostEqual(sized["risk"], 990.0)
        self.assertFalse(sized["capped"])

    def test_a_tighter_stop_buys_more_shares(self):
        # Both stops wide enough to stay under the position cap, or both
        # would cap to the same number and the comparison would show
        # nothing.
        tight = daily_review._size(
            {"ticker": "AAA", "price": 100.0, "stop": 89.0}, 100000.0, 1.0)
        wide = daily_review._size(
            {"ticker": "BBB", "price": 100.0, "stop": 85.0}, 100000.0, 1.0)
        self.assertFalse(tight["capped"])
        self.assertFalse(wide["capped"])
        self.assertGreater(tight["shares"], wide["shares"])
        # Both risk the same dollars, which is the entire point.
        self.assertAlmostEqual(tight["risk"], wide["risk"], delta=100.0)

    def test_a_stop_above_entry_is_refused_rather_than_guessed(self):
        self.assertIsNone(daily_review._size(
            {"ticker": "AAA", "price": 100.0, "stop": 105.0}, 100000.0, 1.0))

    def test_a_missing_stop_is_refused(self):
        self.assertIsNone(daily_review._size(
            {"ticker": "AAA", "price": 100.0, "stop": None}, 100000.0, 1.0))

    def test_a_stop_beyond_the_books_ceiling_is_refused(self):
        # The 15% rule, enforced here as well as in the backtest — this
        # is the path that would actually spend money.
        self.assertIsNone(daily_review._size(
            {"ticker": "AAA", "price": 100.0, "stop": 70.0}, 100000.0, 1.0))

    def test_an_account_too_small_for_one_share_gets_no_suggestion(self):
        self.assertIsNone(daily_review._size(
            {"ticker": "AAA", "price": 5000.0, "stop": 4900.0}, 100.0, 1.0))


class OutputTest(unittest.TestCase):
    def test_every_suggestion_names_a_share_count_and_a_stop(self):
        # Vague output cannot be checked against a chart or scored later.
        book = {"cash": 100000.0, "positions": []}
        candidates = [{"ticker": "AAA", "price": 100.0, "stop": 85.0}]
        text = daily_review.format_review(
            daily_review.review(book, {}, candidates, today=SATURDAY))
        self.assertIn("66 shares", text)
        self.assertIn("85.00", text)

    def test_a_triggered_stop_leads_the_report(self):
        book = {"cash": 0.0, "positions": []}
        bars = _bars([50.0] * 10)
        bars[-1]["low"] = 40.0
        portfolio.add_position(book, "AAA", 100, 50.0, 45.0,
                               entry_date=bars[0]["time"][:10])
        result = daily_review.review(book, {"AAA": bars}, today=WEDNESDAY)
        text = daily_review.format_review(result)
        self.assertTrue(result["urgent"])
        self.assertLess(text.index("STOPS TRIGGERED"), text.index("Check each"))

    def test_the_midweek_report_explains_why_there_are_no_buys(self):
        book = {"cash": 100000.0, "positions": []}
        candidates = [{"ticker": "AAA", "price": 100.0, "stop": 92.0}]
        text = daily_review.format_review(
            daily_review.review(book, {}, candidates, today=WEDNESDAY))
        self.assertIn("still", text)
        self.assertIn("weekend", text)

    def test_the_report_asks_for_what_was_declined_too(self):
        # Declined suggestions are half the forward record.
        text = daily_review.format_review(
            daily_review.review({"cash": 1000.0, "positions": []}, {},
                                today=SATURDAY))
        self.assertIn("decline", text)

    def test_account_value_counts_holdings_at_market_not_cost(self):
        book = {"cash": 1000.0, "positions": []}
        portfolio.add_position(book, "AAA", 100, 50.0, 45.0)
        value = daily_review._account_value(book, {"AAA": _bars([50.0, 80.0])})
        self.assertAlmostEqual(value, 1000.0 + 100 * 80.0)

    def test_no_single_position_exceeds_the_cap_however_tight_the_stop(self):
        # Risk sizing alone would put a quarter of the account into one
        # name if its stop were close enough. A gap through the stop does
        # not care how carefully the position was sized.
        sized = daily_review._size(
            {"ticker": "AAA", "price": 100.0, "stop": 99.5}, 100000.0, 1.0)
        self.assertLessEqual(sized["share_of_account"],
                             daily_review.MAX_POSITION_PCT + 0.01)
        self.assertTrue(sized["capped"])

    def test_a_normally_sized_position_is_not_flagged_as_capped(self):
        # An 8% stop at 1% risk wants 12.5% of the account and does cap.
        # A 15% stop wants 6.7% and does not — which is the range the
        # book's own ceiling puts most setups in.
        sized = daily_review._size(
            {"ticker": "AAA", "price": 100.0, "stop": 85.0}, 100000.0, 1.0)
        self.assertFalse(sized["capped"])

    def test_the_cap_matches_the_backtest_so_the_two_paths_agree(self):
        # A live path that sizes differently from the tested one means
        # the backtest measured a strategy nobody will run.
        from screener import portfolio_sim
        stake = portfolio_sim._stake_for(
            {"return_pct": 10.0, "r_multiple": 2.0}, 100000.0, 1000.0, 1.0,
            100000.0 * daily_review.MAX_POSITION_PCT / 100.0)
        self.assertAlmostEqual(stake, 100000.0 * daily_review.MAX_POSITION_PCT / 100.0)
