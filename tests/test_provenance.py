"""An arm that cannot be recomputed is a claim, not a result.

`parameter_set` records what a run was told to do and nothing about what
it consumed. The W2 and W3 portfolio figures stopped reproducing when
the bar cache they ran against — a symlink into a scratch directory —
was cleaned away. Nothing failed; the numbers simply became
unverifiable while staying quotable.
"""
import os
import tempfile
import unittest

from screener import db


class FingerprintTest(unittest.TestCase):
    def test_a_real_file_fingerprints(self):
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            fh.write(b"x" * 100)
            path = fh.name
        self.addCleanup(os.unlink, path)
        self.assertIsNotNone(db.fingerprint_file(path))

    def test_a_missing_file_is_none_rather_than_an_error(self):
        self.assertIsNone(db.fingerprint_file("/no/such/path.pkl"))

    def test_a_dangling_symlink_is_none(self):
        """The state that actually caused the loss: a path was
        configured and there was nothing behind it."""
        directory = tempfile.mkdtemp()
        link = os.path.join(directory, "cache.pkl")
        os.symlink(os.path.join(directory, "gone.pkl"), link)
        # addCleanup is LIFO, so the directory has to be registered
        # before the link inside it.
        self.addCleanup(os.rmdir, directory)
        self.addCleanup(os.unlink, link)
        self.assertTrue(os.path.islink(link))
        self.assertIsNone(db.fingerprint_file(link))

    def test_the_fingerprint_changes_when_the_file_does(self):
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            fh.write(b"x" * 100)
            path = fh.name
        self.addCleanup(os.unlink, path)
        before = db.fingerprint_file(path)
        with open(path, "wb") as fh:
            fh.write(b"y" * 200)
        self.assertNotEqual(before, db.fingerprint_file(path))


class ProvenanceTest(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        os.unlink(self.path)
        self._previous = db.DB_PATH
        db.DB_PATH = self.path
        db.init_db()
        self.addCleanup(self._restore)

    def _restore(self):
        db.DB_PATH = self._previous
        if os.path.exists(self.path):
            os.unlink(self.path)

    def _trade(self, arm):
        conn = db._connect()
        conn.execute(
            "INSERT INTO backtest_trades (ticker, as_of_date, entry_date, "
            "parameter_set) VALUES ('X','2021-01-01','2021-01-01',?)", (arm,))
        conn.commit()
        conn.close()

    def test_records_and_reads_back(self):
        self._trade("arm1")
        db.record_provenance("arm1", bar_cache_path=self.path)
        row = db.get_provenance("arm1")
        self.assertEqual(row["parameter_set"], "arm1")
        self.assertEqual(row["trade_count"], 1)
        self.assertIsNotNone(row["bar_cache_fingerprint"])

    def test_rerunning_overwrites_rather_than_duplicating(self):
        self._trade("arm1")
        db.record_provenance("arm1", bar_cache_path=self.path)
        db.record_provenance("arm1", bar_cache_path=self.path)
        self.assertEqual(len(db.get_provenance()), 1)

    def test_an_arm_without_provenance_is_reported_as_such(self):
        self._trade("old_arm")
        self.assertIn("old_arm", db.unreproducible_arms()["no_provenance"])

    def test_a_missing_cache_is_reported_as_missing(self):
        self._trade("arm1")
        db.record_provenance("arm1", bar_cache_path="/no/such/cache.pkl")
        self.assertIn("arm1", db.unreproducible_arms()["cache_missing"])

    def test_a_changed_cache_is_reported_as_changed(self):
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            fh.write(b"x" * 100)
            cache = fh.name
        self.addCleanup(os.unlink, cache)
        self._trade("arm1")
        db.record_provenance("arm1", bar_cache_path=cache)
        self.assertIn("arm1", db.unreproducible_arms()["ok"])
        with open(cache, "wb") as fh:
            fh.write(b"y" * 500)
        self.assertIn("arm1", db.unreproducible_arms()["cache_changed"])

    def test_an_unchanged_cache_is_ok(self):
        self._trade("arm1")
        db.record_provenance("arm1", bar_cache_path=self.path)
        self.assertIn("arm1", db.unreproducible_arms()["ok"])



class PortfolioRunTest(unittest.TestCase):
    """A yearly return without its configuration is an opinion.

    The same 6,225 trades of w2_2021_R20 produce +9.54% to +18.69%
    absolute CAGR depending only on account settings. Recording the
    number without the settings is how +12.09% became unidentifiable.
    """

    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        os.unlink(self.path)
        self._previous = db.DB_PATH
        db.DB_PATH = self.path
        db.init_db()
        self.addCleanup(self._restore)

    def _restore(self):
        db.DB_PATH = self._previous
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_records_config_alongside_the_figure(self):
        db.record_portfolio_run(
            "arm1", {"capital": 100000.0, "stake": 1000.0, "risk_pct": None},
            {"cagr_pct": 12.09, "skipped": 3832, "taken": 2393},
            benchmark="IWM", benchmark_cagr_pct=6.13)
        rows = db.get_portfolio_runs("arm1")
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["cagr_pct"], 12.09)
        self.assertEqual(rows[0]["benchmark"], "IWM")
        self.assertEqual(rows[0]["config"]["capital"], 100000.0)

    def test_config_round_trips_as_a_dict_not_a_string(self):
        db.record_portfolio_run("arm1", {"risk_pct": 0.75}, {"cagr_pct": 1.0})
        self.assertIsInstance(db.get_portfolio_runs("arm1")[0]["config"], dict)

    def test_a_none_in_the_config_survives(self):
        """risk_pct=None and risk_pct absent are different runs, and the
        difference is worth several points."""
        db.record_portfolio_run("arm1", {"risk_pct": None}, {"cagr_pct": 1.0})
        config = db.get_portfolio_runs("arm1")[0]["config"]
        self.assertIn("risk_pct", config)
        self.assertIsNone(config["risk_pct"])

    def test_two_configs_for_one_arm_are_both_kept(self):
        """Re-running under different settings is a second result, not a
        correction of the first."""
        import time
        db.record_portfolio_run("arm1", {"risk_pct": None}, {"cagr_pct": 9.54})
        time.sleep(1.01)
        db.record_portfolio_run("arm1", {"risk_pct": 0.75}, {"cagr_pct": 18.69})
        rows = db.get_portfolio_runs("arm1")
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["cagr_pct"] for r in rows}, {9.54, 18.69})

if __name__ == "__main__":
    unittest.main()
