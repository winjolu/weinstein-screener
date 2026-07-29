"""Regressions for the local market-history cache.

The cache is a quarter-hour of API calls, so the failure modes that
matter are the quiet ones: a truncated file that loads as garbage, or a
read that silently triggers a rebuild.
"""
import os
import pickle
import tempfile
import unittest

from screener import bar_cache


def _bars(n):
    return [{"time": f"2020-01-{i%28+1:02d}T00:00:00.000+0000", "open": 1.0,
             "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0} for i in range(n)]


class BuildAndLoadTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._dir.name, "bars.pkl")
        bar_cache._loaded = None
        bar_cache._loaded_path = None
        self._real = bar_cache.data_fetch.get_weekly_bars_batch

    def tearDown(self):
        bar_cache.data_fetch.get_weekly_bars_batch = self._real
        bar_cache._loaded = None
        bar_cache._loaded_path = None
        self._dir.cleanup()

    def _fake_fetch(self, missing=()):
        def fake(chunk, lookback_weeks=None):
            return {s: _bars(10) for s in chunk if s not in missing}
        bar_cache.data_fetch.get_weekly_bars_batch = fake

    def test_build_then_load_round_trips(self):
        self._fake_fetch()
        bar_cache.build(["AAA", "BBB"], path=self.path, progress=False)
        loaded = bar_cache.load(self.path)
        self.assertEqual(sorted(loaded), ["AAA", "BBB"])
        self.assertEqual(len(loaded["AAA"]), 10)

    def test_symbols_with_no_data_are_absent_not_empty(self):
        """An empty list would read downstream as 'no history', which is
        a different thing from 'the API has never heard of this'."""
        self._fake_fetch(missing={"DEAD"})
        bar_cache.build(["AAA", "DEAD"], path=self.path, progress=False)
        loaded = bar_cache.load(self.path)
        self.assertIn("AAA", loaded)
        self.assertNotIn("DEAD", loaded)

    def test_load_refuses_to_rebuild_silently(self):
        """Fifteen minutes of API calls must not happen as a side effect
        of a read, and the error has to say how to fix it — a bare
        FileNotFoundError from open() would satisfy the exception type
        while telling the reader nothing."""
        with self.assertRaises(FileNotFoundError) as caught:
            bar_cache.load(os.path.join(self._dir.name, "absent.pkl"))
        self.assertIn("build", str(caught.exception).lower())

    def test_no_partial_file_is_left_behind(self):
        self._fake_fetch()
        bar_cache.build(["AAA"], path=self.path, progress=False)
        self.assertFalse(os.path.exists(self.path + ".partial"))

    def test_a_truncated_cache_does_not_masquerade_as_valid(self):
        """The write goes to a temporary name and is renamed, so a crash
        mid-dump leaves the old cache rather than a corrupt one."""
        with open(self.path + ".partial", "wb") as fh:
            fh.write(b"\x80\x04 truncated garbage")
        self._fake_fetch()
        bar_cache.build(["AAA"], path=self.path, progress=False)
        self.assertEqual(sorted(bar_cache.load(self.path)), ["AAA"])

    def test_info_reports_without_returning_bars(self):
        self._fake_fetch()
        bar_cache.build(["AAA", "BBB"], path=self.path, progress=False)
        meta = bar_cache.info(self.path)
        self.assertEqual(meta["symbols"], 2)
        self.assertEqual(meta["total_bars"], 20)
        self.assertNotIn("bars", meta)

    def test_info_on_a_missing_cache_is_none_not_an_error(self):
        self.assertIsNone(bar_cache.info(os.path.join(self._dir.name, "nope.pkl")))

    def test_with_history_filters_on_depth(self):
        def fake(chunk, lookback_weeks=None):
            return {"SHORT": _bars(5), "LONG": _bars(500)}
        bar_cache.data_fetch.get_weekly_bars_batch = fake
        bar_cache.build(["SHORT", "LONG"], path=self.path, progress=False)
        self.assertEqual(bar_cache.with_history(100, self.path), ["LONG"])

    def test_load_is_memoised_per_path(self):
        self._fake_fetch()
        bar_cache.build(["AAA"], path=self.path, progress=False)
        first = bar_cache.load(self.path)
        os.remove(self.path)
        self.assertIs(bar_cache.load(self.path), first)
