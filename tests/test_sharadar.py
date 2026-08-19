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


class RefreshTest(_Stubbed):
    """Topping up the local database from the API.

    The bulk export is a snapshot and stale by the next close. Anything
    needing today's data has to fetch incrementally — re-downloading 6GB
    to add one day is how a daily refresh becomes something nobody runs.
    """

    def _db(self):
        import sqlite3, tempfile, os
        fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
        conn.executemany("INSERT INTO prices VALUES (?,?,?)",
                         [("AAPL", "2026-08-03", 100.0), ("AAPL", "2026-08-04", 101.0)])
        conn.commit(); conn.close()
        self.addCleanup(os.remove, path)
        return path

    def test_it_asks_only_for_dates_after_what_we_hold(self):
        path = self._db()
        self.stub([[]])
        sharadar.refresh("prices", db_path=path)
        self.assertEqual(self.calls[0][1]["date.gt"], "2026-08-04")

    def test_new_rows_are_appended(self):
        path = self._db()
        self.stub([[{"ticker": "AAPL", "date": "2026-08-05", "close": "102.0"}]])
        added = sharadar.refresh("prices", db_path=path)
        self.assertEqual(added, 1)
        import sqlite3
        conn = sqlite3.connect(path)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0], 3)
        conn.close()

    def test_running_twice_in_a_day_adds_nothing(self):
        path = self._db()
        self.stub([[], []])
        self.assertEqual(sharadar.refresh("prices", db_path=path), 0)
        self.assertEqual(sharadar.refresh("prices", db_path=path), 0)

    def test_an_empty_table_refuses_rather_than_backfilling_one_day_at_a_time(self):
        import sqlite3, tempfile, os
        fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
        conn.commit(); conn.close()
        self.addCleanup(os.remove, path)
        with self.assertRaises(ValueError):
            sharadar.refresh("prices", db_path=path)

    def test_an_unknown_table_raises_rather_than_guessing_the_date_column(self):
        # Guessing wrong produces an empty refresh that reads as "no new
        # data" instead of an error, which is the worst possible failure.
        with self.assertRaises(ValueError):
            sharadar.latest_local_date("some_new_table", db_path=self._db())

    def test_the_api_table_name_is_translated(self):
        # Local `prices` comes from the API's `stocks`. Sending the local
        # name would query a table that does not exist.
        path = self._db()
        self.stub([[]])
        sharadar.refresh("prices", db_path=path)
        self.assertEqual(self.calls[0][0], "stocks")


class ArchivalGuardTest(unittest.TestCase):
    """History a shorter entitlement cannot replace must be unwritable.

    The bulk loaders are destructive by design — one drops a table, one
    removes the database file. That was safe while the subscription
    carried full depth. It is not safe now: a rebuild replaces decades
    with twelve months and nothing can restore the difference.
    """

    def _db(self, rows=(("2005-01-03", 10.0), ("2026-08-03", 20.0))):
        import os
        import sqlite3
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.remove, path)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
        conn.executemany("INSERT INTO prices VALUES ('AAA',?,?)", rows)
        conn.commit()
        conn.close()
        return path

    def test_freezing_counts_the_rows_it_protects(self):
        path = self._db()
        held = sharadar.freeze_history("prices", "2025-08-11", db_path=path)
        self.assertEqual(held, 1)
        self.assertEqual(sharadar.frozen_before("prices", db_path=path), "2025-08-11")

    def test_an_unfrozen_table_is_refused_rather_than_waved_through(self):
        # This assertion used to read the other way, permitting a write
        # when no watermark existed. That is precisely how the guard sat
        # inert for weeks: an absent watermark is indistinguishable from
        # a guard nobody armed, and failing open looks identical to
        # passing. The shared implementation refuses, and adopting it is
        # what made this test fail rather than any change of mine.
        path = self._db()
        with self.assertRaises(sharadar.ArchivalWrite):
            sharadar.assert_writable("prices", "1990-01-01", db_path=path)

    def test_a_genuine_first_load_can_say_so_explicitly(self):
        # The escape hatch has to exist or the first bulk load is
        # impossible, but it must be asked for rather than assumed.
        path = self._db()
        sharadar.assert_writable("prices", "1990-01-01", db_path=path,
                                 unfrozen_ok=True)

    def test_reaching_below_the_watermark_is_refused(self):
        path = self._db()
        sharadar.freeze_history("prices", "2025-08-11", db_path=path)
        with self.assertRaises(sharadar.ArchivalWrite):
            sharadar.assert_writable("prices", "2010-01-01", db_path=path)

    def test_appending_after_the_watermark_is_allowed(self):
        # The guard has to permit the daily refresh, or it will be
        # switched off and protect nothing.
        path = self._db()
        sharadar.freeze_history("prices", "2025-08-11", db_path=path)
        sharadar.assert_writable("prices", "2026-08-04", db_path=path)

    def test_the_boundary_date_itself_is_writable(self):
        # frozen_before is exclusive: rows *before* it are archival, so
        # an operation starting exactly at the watermark is fine.
        path = self._db()
        sharadar.freeze_history("prices", "2025-08-11", db_path=path)
        sharadar.assert_writable("prices", "2025-08-11", db_path=path)

    def test_freezing_is_idempotent_rather_than_accumulating(self):
        path = self._db()
        sharadar.freeze_history("prices", "2025-08-11", db_path=path)
        sharadar.freeze_history("prices", "2025-08-11", db_path=path)
        import sqlite3
        conn = sqlite3.connect(path)
        n = conn.execute("SELECT COUNT(*) FROM data_coverage").fetchone()[0]
        conn.close()
        self.assertEqual(n, 1)


class RefreshGapTest(_Stubbed):
    """An append that leaves an unfillable hole must fail, not succeed.

    refresh() asks for rows after the newest stored. Once the local data
    has fallen further behind than the entitlement reaches, the earliest
    row the API can return sits past the gap — and appending it writes a
    hole into the middle of the series while reporting success. A silent
    hole is worse than a failed refresh, because every later read treats
    it as real absence.
    """

    def _db(self, newest="2026-08-03"):
        import os
        import sqlite3
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.remove, path)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
        conn.execute("INSERT INTO prices VALUES ('AAA',?,1.0)", (newest,))
        conn.commit()
        conn.close()
        return path

    def test_a_contiguous_append_succeeds(self):
        path = self._db("2026-08-03")
        self.stub([[{"ticker": "AAA", "date": "2026-08-04", "close": "2.0"}]])
        self.assertEqual(sharadar.refresh("prices", db_path=path), 1)

    def test_a_hole_larger_than_the_window_raises(self):
        path = self._db("2026-08-03")
        self.stub([[{"ticker": "AAA", "date": "2027-06-01", "close": "2.0"}]])
        with self.assertRaises(sharadar.RefreshGap):
            sharadar.refresh("prices", db_path=path)

    def test_the_hole_is_reported_before_anything_is_written(self):
        # The failure has to happen before the insert, or the guard just
        # describes damage it has already done.
        import sqlite3
        path = self._db("2026-08-03")
        self.stub([[{"ticker": "AAA", "date": "2027-06-01", "close": "2.0"}]])
        with self.assertRaises(sharadar.RefreshGap):
            sharadar.refresh("prices", db_path=path)
        conn = sqlite3.connect(path)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0], 1)
        conn.close()

    def test_a_deliberate_override_still_works(self):
        path = self._db("2026-08-03")
        self.stub([[{"ticker": "AAA", "date": "2027-06-01", "close": "2.0"}]])
        self.assertEqual(
            sharadar.refresh("prices", db_path=path, allow_gap=True), 1)


class FundamentalsDateColumnTest(unittest.TestCase):
    def test_fundamentals_keys_on_datekey_not_calendardate(self):
        # A company filing six months late carries an old calendardate
        # and a new datekey. Keying the refresh on calendardate asks for
        # dates after the newest stored and never sees that filing —
        # permanently, and slow filers are not a random sample.
        self.assertEqual(sharadar.DATE_COLUMN["fundamentals"], "datekey")
