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


if __name__ == "__main__":
    unittest.main()
