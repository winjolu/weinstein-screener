"""Storage-layer regressions.

The schema-on-connect behaviour is here because the failure it prevents
is genuinely confusing: once data_fetch started consulting the sector
cache, any caller that hadn't happened to run init_db() first got an
OperationalError about a missing table, raised from somewhere that had
nothing obviously to do with the database.
"""
import os
import tempfile
import sqlite3
import unittest

from screener import db


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


class SchemaBootstrapTest(_TempDB):
    def test_tables_exist_without_an_explicit_init(self):
        """No init_db() call anywhere in this test."""
        self.assertIsNone(db.get_cached_sector("AAPL"))
        self.assertIsNone(db.get_cached_universe())
        self.assertEqual(db.get_backtest_trades(), [])

    def test_switching_db_path_reapplies_schema(self):
        db.cache_sector("AAPL", "Software & IT Services")
        with tempfile.TemporaryDirectory() as other:
            db.DB_PATH = os.path.join(other, "data", "other.db")
            # A stale "already done" flag here would leave this file
            # schema-less and raise instead of returning None.
            self.assertIsNone(db.get_cached_sector("AAPL"))


class SectorCacheTest(_TempDB):
    def test_round_trip(self):
        db.cache_sector("AAPL", "Software & IT Services")
        self.assertEqual(db.get_cached_sector("AAPL")["sector"], "Software & IT Services")

    def test_cached_null_is_distinguishable_from_absent(self):
        """ETFs legitimately have no sector. A cached None has to read as
        "asked and got nothing" rather than "never asked", or every scan
        re-fetches every ETF forever.
        """
        db.cache_sector("SPY", None)
        cached = db.get_cached_sector("SPY")
        self.assertIsNotNone(cached)
        self.assertIsNone(cached["sector"])
        self.assertIsNone(db.get_cached_sector("NEVER_SEEN"))

    def test_stale_entries_are_ignored(self):
        db.cache_sector("AAPL", "Software & IT Services")
        conn = db._connect()
        conn.execute("UPDATE sector_cache SET fetched_date = ? WHERE ticker = ?",
                     ("2000-01-01", "AAPL"))
        conn.commit()
        conn.close()
        self.assertIsNone(db.get_cached_sector("AAPL"))


class UniverseCacheTest(_TempDB):
    def test_replaces_wholesale_so_delistings_disappear(self):
        db.cache_universe([{"symbol": "AAA", "name": "A", "exchange_code": "NYSE", "status": "OC"},
                           {"symbol": "BBB", "name": "B", "exchange_code": "NYSE", "status": "OC"}])
        db.cache_universe([{"symbol": "AAA", "name": "A", "exchange_code": "NYSE", "status": "OC"}])
        symbols = [row["symbol"] for row in db.get_cached_universe()]
        self.assertEqual(symbols, ["AAA"])

    def test_skips_rows_without_a_symbol(self):
        db.cache_universe([{"symbol": None, "name": "junk"},
                           {"symbol": "AAA", "name": "A", "exchange_code": "NYSE", "status": "OC"}])
        self.assertEqual(len(db.get_cached_universe()), 1)


class ScreenerResultTest(_TempDB):
    def _row(self, ticker="AAA", run_date="2026-07-26", **overrides):
        base = {"ticker": ticker, "run_date": run_date, "stage": 2, "conditions_met": 8,
                "conditions_detail": {"scoring": {"actionable": True}}, "price": 100.0}
        base.update(overrides)
        return base

    def test_rerunning_the_same_day_replaces_rather_than_accumulates(self):
        """Two scans in one day used to leave two rows per ticker, and
        get_latest_results returned both — double-counting everything
        downstream.
        """
        db.insert_result(self._row(price=100.0))
        db.insert_result(self._row(price=111.0))
        rows = db.get_latest_results()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["price"], 111.0)

    def test_separate_days_are_both_kept(self):
        db.insert_result(self._row(run_date="2026-07-25"))
        db.insert_result(self._row(run_date="2026-07-26"))
        self.assertEqual(len(db.get_ticker_history("AAA", 10)), 2)

    def test_distinct_tickers_coexist(self):
        db.insert_result(self._row(ticker="AAA"))
        db.insert_result(self._row(ticker="BBB"))
        self.assertEqual(len(db.get_latest_results()), 2)


class BacktestTradeTest(_TempDB):
    def _trade(self, **overrides):
        base = {
            "ticker": "AAA", "as_of_date": "2025-01-06", "entry_date": "2025-01-06",
            "entry_price": 100.0, "exit_date": "2025-03-01", "exit_price": 110.0,
            "exit_reason": "target", "return_pct": 10.0, "r_multiple": 1.5,
            "conditions_met": 8, "parameter_set": "baseline", "still_open": False,
        }
        base.update(overrides)
        return base

    def test_filters_by_parameter_set(self):
        db.insert_backtest_trade(self._trade(parameter_set="baseline"))
        db.insert_backtest_trade(self._trade(parameter_set="variant"))
        self.assertEqual(len(db.get_backtest_trades(parameter_set="baseline")), 1)
        self.assertEqual(len(db.get_backtest_trades()), 2)

    def test_rerunning_a_parameter_set_replaces_rather_than_doubles(self):
        """Re-running the same backtest used to append a second copy of
        every trade, silently doubling the sample the report aggregates.
        """
        db.insert_backtest_trade(self._trade(exit_price=110.0, return_pct=10.0))
        db.insert_backtest_trade(self._trade(exit_price=120.0, return_pct=20.0))
        rows = db.get_backtest_trades()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["return_pct"], 20.0)

    def test_the_same_ticker_may_hold_several_trades_at_different_entries(self):
        """Sequential non-overlapping trades in one ticker are real and
        must survive deduplication."""
        db.insert_backtest_trade(self._trade(entry_date="2025-01-06"))
        db.insert_backtest_trade(self._trade(entry_date="2025-06-02"))
        self.assertEqual(len(db.get_backtest_trades()), 2)

    def test_the_same_trade_under_two_parameter_sets_is_two_observations(self):
        """A/B comparison depends on the same trade appearing once per
        parameter set."""
        db.insert_backtest_trade(self._trade(parameter_set="baseline"))
        db.insert_backtest_trade(self._trade(parameter_set="pivot_length=10"))
        self.assertEqual(len(db.get_backtest_trades()), 2)


if __name__ == "__main__":
    unittest.main()


class SecurityIdentityCacheTest(_TempDB):
    """Ticker ownership, cached so EDGAR is asked once rather than per run.

    The failure this guards against isn't a crash: a recycled ticker
    returns a complete, well-formed series stitched together from two
    unrelated companies.
    """

    IBM = {"ticker": "IBM", "cik": 51143, "company_name": "INTERNATIONAL BUSINESS MACHINES",
           "first_filing_date": "1994-01-01", "former_names": [],
           "delisted_date": None, "delisting_form": None}
    GM = {"ticker": "GM", "cik": 1467858, "company_name": "General Motors Co",
          "first_filing_date": "2009-07-16", "former_names": [],
          "delisted_date": None, "delisting_form": None}

    def test_an_identity_survives_the_round_trip(self):
        db.cache_identities([self.GM])
        got = db.get_cached_identity("GM")
        self.assertEqual(got["cik"], 1467858)
        self.assertEqual(got["first_filing_date"], "2009-07-16")

    def test_former_names_round_trip_as_a_list(self):
        # Stored as JSON, so a bare string would come back as characters.
        db.cache_identities([dict(self.IBM, former_names=["USA WASTE SERVICES INC"])])
        self.assertEqual(db.get_cached_identity("IBM")["former_names"],
                         ["USA WASTE SERVICES INC"])

    def test_a_ticker_with_no_filer_is_a_cached_answer_not_a_miss(self):
        # ETFs and foreign issues have no SEC filer. Recording that costs
        # one row and saves looking it up again forever; treating it as a
        # miss would re-fetch every one of them on every run.
        db.cache_identities([{"ticker": "XYZ", "cik": None, "company_name": None,
                              "first_filing_date": None, "former_names": [],
                              "delisted_date": None, "delisting_form": None}])
        got = db.get_cached_identity("XYZ")
        self.assertIsNotNone(got)
        self.assertIsNone(got["cik"])
        self.assertEqual(db.tickers_needing_identity(["XYZ"]), [])

    def test_only_unresolved_tickers_are_reported_as_needing_work(self):
        db.cache_identities([self.GM])
        self.assertEqual(db.tickers_needing_identity(["GM", "AAPL"]), ["AAPL"])

    def test_a_stale_row_is_refetched(self):
        db.cache_identities([self.GM])
        conn = db._connect()
        conn.execute("UPDATE security_identity SET fetched_date = '2000-01-01'")
        conn.commit()
        conn.close()
        self.assertIsNone(db.get_cached_identity("GM"))
        self.assertEqual(db.tickers_needing_identity(["GM"]), ["GM"])

    def test_bars_before_the_owner_existed_are_flagged(self):
        # The real case: General Motors Co first filed in 2009, so 2008
        # bars under GM belong to the company that went bankrupt.
        db.cache_identities([self.GM])
        bars = [{"time": "2008-05-30T00:00:00.000+00:00", "close": 17.0},
                {"time": "2011-05-30T00:00:00.000+00:00", "close": 31.0}]
        bad = db.bars_predating_owner("GM", bars)
        self.assertEqual(len(bad), 1)
        self.assertTrue(bad[0]["time"].startswith("2008"))

    def test_a_clean_series_flags_nothing(self):
        db.cache_identities([self.IBM])
        bars = [{"time": "2005-01-03T00:00:00.000+00:00", "close": 90.0}]
        self.assertEqual(db.bars_predating_owner("IBM", bars), [])

    def test_an_unknown_ticker_flags_nothing_rather_than_everything(self):
        # Silence about a symbol we never resolved is not evidence its
        # history is wrong. Discarding real bars on a missing lookup
        # would be the more damaging error of the two.
        bars = [{"time": "1995-01-03T00:00:00.000+00:00", "close": 5.0}]
        self.assertEqual(db.bars_predating_owner("NEVERSEEN", bars), [])

    def test_a_second_write_updates_rather_than_duplicates(self):
        db.cache_identities([self.GM])
        db.cache_identities([dict(self.GM, company_name="GENERAL MOTORS CO")])
        conn = db._connect()
        n = conn.execute("SELECT COUNT(*) FROM security_identity WHERE ticker='GM'").fetchone()[0]
        conn.close()
        self.assertEqual(n, 1)
        self.assertEqual(db.get_cached_identity("GM")["company_name"], "GENERAL MOTORS CO")


class BusyTimeoutTest(unittest.TestCase):
    """A locked database must be waited on, not surrendered to.

    Two arms running concurrently killed a four-hour sweep in its final
    band. The default five seconds is not a considered choice, it is
    Python's default, and it is far inside what a write costs when the
    file sits in a folder a sync client is also touching.
    """

    def test_the_connection_waits_a_full_minute_for_a_lock(self):
        conn = db._connect()
        try:
            self.assertGreaterEqual(
                conn.execute("PRAGMA busy_timeout").fetchone()[0], 60000)
        finally:
            conn.close()


class MergeBacktestTradesTest(unittest.TestCase):
    """Folding a side database's arms back into the main one.

    A long arm writes to local disk to keep 80,000 write transactions out
    of a synced folder. That is only safe if bringing the results home is
    exact.
    """

    def _side(self, rows):
        import os as _os
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".db"); _os.close(fd)
        self.addCleanup(_os.remove, path)
        prev = db.DB_PATH
        db.DB_PATH = path
        db._schema_ready_for = None
        try:
            for r in rows:
                db.insert_backtest_trade(r)
        finally:
            db.DB_PATH = prev
            db._schema_ready_for = None
        return path

    def _main(self):
        import os as _os
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".db"); _os.close(fd)
        self.addCleanup(_os.remove, path)
        return path

    def _trade(self, ticker, tag, entry="2020-01-06"):
        return {"ticker": ticker, "as_of_date": entry,
                "entry_date": entry, "exit_date": "2020-03-02",
                "entry_price": 10.0, "exit_price": 11.0, "return_pct": 10.0,
                "parameter_set": tag, "still_open": 0}

    def test_rows_arrive_in_the_main_database(self):
        side = self._side([self._trade("AAA", "x1"), self._trade("BBB", "x1")])
        main = self._main()
        self.assertEqual(db.merge_backtest_trades(side, db_path=main), 2)
        conn = sqlite3.connect(main)
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM backtest_trades").fetchone()[0], 2)
        conn.close()

    def test_merging_the_same_arm_twice_replaces_rather_than_doubles(self):
        # A doubled arm does not error, it just reports twice the trades
        # at the same statistics — which reads as a real result.
        side = self._side([self._trade("AAA", "x1")])
        main = self._main()
        db.merge_backtest_trades(side, db_path=main)
        db.merge_backtest_trades(side, db_path=main)
        conn = sqlite3.connect(main)
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM backtest_trades").fetchone()[0], 1)
        conn.close()

    def test_an_unrelated_arm_already_present_is_left_alone(self):
        main = self._main()
        prev = db.DB_PATH
        db.DB_PATH = main; db._schema_ready_for = None
        try:
            db.insert_backtest_trade(self._trade("ZZZ", "keepme"))
        finally:
            db.DB_PATH = prev; db._schema_ready_for = None
        side = self._side([self._trade("AAA", "x1")])
        db.merge_backtest_trades(side, db_path=main)
        conn = sqlite3.connect(main)
        tags = {r[0] for r in conn.execute("SELECT DISTINCT parameter_set FROM backtest_trades")}
        self.assertEqual(tags, {"keepme", "x1"})
        conn.close()

    def test_the_values_survive_the_trip(self):
        side = self._side([self._trade("AAA", "x1")])
        main = self._main()
        db.merge_backtest_trades(side, db_path=main)
        conn = sqlite3.connect(main); conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM backtest_trades").fetchone()
        self.assertEqual(row["ticker"], "AAA")
        self.assertAlmostEqual(row["return_pct"], 10.0)
        self.assertEqual(row["parameter_set"], "x1")
        conn.close()
