"""Storage-layer regressions.

The schema-on-connect behaviour is here because the failure it prevents
is genuinely confusing: once data_fetch started consulting the sector
cache, any caller that hadn't happened to run init_db() first got an
OperationalError about a missing table, raised from somewhere that had
nothing obviously to do with the database.
"""
import os
import tempfile
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
