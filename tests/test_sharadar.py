"""Sharadar client.

Nothing here touches the network. The CSV fixtures are trimmed copies of
real responses captured on 2026-08-03, because a fixture invented from
memory tests my memory rather than the parser — and my memory of this
API was wrong on the first attempt, which is the reason the module
exists in this shape.
"""
import os
import unittest

from screener import sharadar


AAPL_CSV = (
    "ticker,date,open,high,low,close,volume,closeadj,closeunadj,lastupdated\n"
    "AAPL,2026-07-31,304.81,310.69,300,308.91,127398000,308.91,308.91,2026-08-01\n"
    "AAPL,2026-07-30,333.13,334.75,329.59,333.43,55502000,333.43,333.43,2026-08-01\n"
)

# A dividend payer, where closeadj and close diverge. This is the case
# that breaks a naive reader.
DIV_CSV = (
    "ticker,date,open,high,low,close,volume,closeadj,closeunadj,lastupdated\n"
    "KO,2020-01-02,50.0,52.0,49.0,50.0,1000000,25.0,50.0,2026-01-01\n"
)

TICKERS_CSV = (
    "table,permaticker,ticker,name,exchange,isdelisted,category,sector\n"
    "SEP,199059,AAPL,Apple Inc,NASDAQ,N,Domestic Common Stock,Technology\n"
    "SEP,120568,LEH,Lehman Brothers Holdings Inc,NYSE,Y,Domestic Common Stock,Financials\n"
)


class _Stubbed(unittest.TestCase):
    def setUp(self):
        self._prev = sharadar._get
        self._prev_key = os.environ.get("SHARADAR_API_KEY")
        os.environ["SHARADAR_API_KEY"] = "test-key"
        self.calls = []

    def tearDown(self):
        sharadar._get = self._prev
        if self._prev_key is None:
            os.environ.pop("SHARADAR_API_KEY", None)
        else:
            os.environ["SHARADAR_API_KEY"] = self._prev_key

    def stub(self, pages):
        """pages: list of row-lists, returned in order."""
        queue = list(pages)

        def fake(table, **params):
            self.calls.append((table, params))
            return queue.pop(0) if queue else []

        sharadar._get = fake

    def rows(self, csv_text):
        import csv as _csv
        import io as _io
        return list(_csv.DictReader(_io.StringIO(csv_text)))


class ApiKeyTest(unittest.TestCase):
    def test_a_missing_key_raises_rather_than_returning_nothing(self):
        # An unauthenticated request returns an empty result that reads
        # as "this company has no data" — the exact wrong conclusion in a
        # module built to tell absence from non-existence.
        prev = os.environ.pop("SHARADAR_API_KEY", None)
        try:
            with self.assertRaises(sharadar.MissingApiKey):
                sharadar._api_key()
        finally:
            if prev is not None:
                os.environ["SHARADAR_API_KEY"] = prev

    def test_a_blank_key_is_treated_as_missing(self):
        prev = os.environ.get("SHARADAR_API_KEY")
        os.environ["SHARADAR_API_KEY"] = "   "
        try:
            with self.assertRaises(sharadar.MissingApiKey):
                sharadar._api_key()
        finally:
            if prev is None:
                os.environ.pop("SHARADAR_API_KEY", None)
            else:
                os.environ["SHARADAR_API_KEY"] = prev


class PaginationTest(_Stubbed):
    def test_a_short_page_ends_the_walk(self):
        self.stub([[{"a": "1"}] * 10000, [{"a": "2"}] * 3])
        rows = sharadar.fetch("stocks")
        self.assertEqual(len(rows), 10003)
        self.assertEqual(len(self.calls), 2)

    def test_the_offset_advances_by_the_page_size(self):
        self.stub([[{"a": "1"}] * 10000, []])
        sharadar.fetch("stocks")
        self.assertEqual(self.calls[0][1]["skip"], 0)
        self.assertEqual(self.calls[1][1]["skip"], 10000)

    def test_a_single_short_page_makes_one_request(self):
        self.stub([[{"a": "1"}] * 5])
        self.assertEqual(len(sharadar.fetch("stocks")), 5)
        self.assertEqual(len(self.calls), 1)

    def test_an_exactly_full_final_page_is_not_assumed_to_be_the_end(self):
        # 10000 rows could be a full page or the whole answer. Stopping
        # there would silently truncate; the API gives no total, so the
        # only safe read is to ask again.
        self.stub([[{"a": "1"}] * 10000, []])
        sharadar.fetch("stocks")
        self.assertEqual(len(self.calls), 2)


class BarShapeTest(_Stubbed):
    def test_bars_match_the_shape_used_elsewhere(self):
        self.stub([self.rows(AAPL_CSV)])
        bars = sharadar.daily_bars("AAPL")
        self.assertEqual(len(bars), 2)
        for field in ("time", "open", "high", "low", "close", "volume"):
            self.assertIn(field, bars[0])
        self.assertTrue(bars[0]["time"].startswith("2026-07-30T"))

    def test_bars_come_back_oldest_first(self):
        # The API returns newest first; every consumer here assumes the
        # opposite, and a reversed series produces confident nonsense.
        self.stub([self.rows(AAPL_CSV)])
        bars = sharadar.daily_bars("AAPL")
        self.assertLess(bars[0]["time"], bars[1]["time"])

    def test_the_dividend_adjusted_close_is_used(self):
        self.stub([self.rows(DIV_CSV)])
        self.assertAlmostEqual(sharadar.daily_bars("KO")[0]["close"], 25.0)

    def test_open_high_low_are_scaled_with_the_close(self):
        # closeadj is half of close here, so the whole bar halves. Taking
        # the adjusted close while leaving the others raw would put the
        # close outside its own high-low range — which stop and target
        # logic would act on without complaint.
        self.stub([self.rows(DIV_CSV)])
        bar = sharadar.daily_bars("KO")[0]
        self.assertAlmostEqual(bar["open"], 25.0)
        self.assertAlmostEqual(bar["high"], 26.0)
        self.assertAlmostEqual(bar["low"], 24.5)
        self.assertLessEqual(bar["close"], bar["high"])
        self.assertGreaterEqual(bar["close"], bar["low"])

    def test_date_bounds_are_passed_through(self):
        self.stub([[]])
        sharadar.daily_bars("AAPL", start="2005-01-01", end="2009-12-31")
        params = self.calls[0][1]
        self.assertEqual(params["date.gte"], "2005-01-01")
        self.assertEqual(params["date.lte"], "2009-12-31")

    def test_a_row_with_no_usable_price_is_skipped_not_zeroed(self):
        self.stub([self.rows(
            "ticker,date,open,high,low,close,volume,closeadj\n"
            "X,2020-01-02,,,,,,\n")])
        self.assertEqual(sharadar.daily_bars("X"), [])


class DelistedTest(_Stubbed):
    def test_the_delisted_flag_is_parsed_as_a_boolean(self):
        self.stub([self.rows(TICKERS_CSV)])
        rows = {r["ticker"]: r for r in sharadar.ticker_metadata()}
        self.assertFalse(rows["AAPL"]["isdelisted"])
        self.assertTrue(rows["LEH"]["isdelisted"])

    def test_delisted_tickers_returns_only_the_dead(self):
        self.stub([self.rows(TICKERS_CSV)])
        dead = sharadar.delisted_tickers()
        self.assertEqual([r["ticker"] for r in dead], ["LEH"])

    def test_the_permanent_identifier_is_kept(self):
        # A ticker is not an identity — GM, WM and CC all resolve to
        # companies that did not hold those symbols during the periods
        # tested here. permaticker is what makes that detectable.
        self.stub([self.rows(TICKERS_CSV)])
        rows = {r["ticker"]: r for r in sharadar.ticker_metadata()}
        self.assertEqual(rows["LEH"]["permaticker"], "120568")
        self.assertNotEqual(rows["LEH"]["permaticker"], rows["AAPL"]["permaticker"])
