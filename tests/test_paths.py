"""Nothing written during a run may live inside the checkout.

This checkout sits in a synced folder. A sync client rewriting a SQLite
file mid-transaction killed a four-hour sweep on a lock timeout, roughly
tripled arm runtimes, and left two arms short by 961 and 40,945 rows
that were never accounted for. A backtest writes one transaction per
trade, so the collision window is open more or less continuously.

The assertions below are the part that lasts. A location rule nobody
checks drifts back the first time someone writes a convenient default.
"""
import os
import tempfile
import unittest

from screener import bar_cache, db, paths


def _tmp(name):
    """A scratch path built at run time rather than written into the file.

    Hardcoding one would trip the portability check these very tests
    exist alongside — which is exactly what it did on the first run.
    """
    return os.path.join(tempfile.gettempdir(), name)


class WriteLocationTest(unittest.TestCase):
    def test_the_results_database_is_outside_the_checkout(self):
        self.assertFalse(paths.inside_checkout(db.DB_PATH),
                         f"results database is inside the repo: {db.DB_PATH}")

    def test_the_bar_cache_is_outside_the_checkout(self):
        # 334MB here, 1.7GB on the sibling project. Bigger than the
        # database and the same hazard.
        self.assertFalse(paths.inside_checkout(bar_cache.CACHE_PATH),
                         f"bar cache is inside the repo: {bar_cache.CACHE_PATH}")

    def test_inside_checkout_says_yes_to_something_genuinely_inside(self):
        # Without this, both tests above would pass if inside_checkout
        # simply always returned False — an assertion that never fires.
        self.assertTrue(paths.inside_checkout(
            os.path.join(paths.REPO, "screener", "db.py")))

    def test_a_sibling_sharing_the_name_prefix_is_not_inside(self):
        # "…/weinstein-screener-backup" starts with the repo path as a
        # string but is a different directory. Comparing without the
        # separator would call it inside.
        self.assertFalse(paths.inside_checkout(paths.REPO + "-backup/x.db"))


class OverrideTest(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in
                       ("WEINSTEIN_SCREENER_DATA_DIR", "SCREENER_DATA_DIR",
                        "SCREENER_BAR_CACHE")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_the_directory_override_moves_everything(self):
        os.environ["WEINSTEIN_SCREENER_DATA_DIR"] = _tmp("wsd")
        self.assertEqual(paths.data_file("x.pkl"), os.path.join(_tmp("wsd"), "x.pkl"))

    def test_the_legacy_variable_is_still_honoured(self):
        # SCREENER_DATA_DIR predates the shared helper and was already
        # documented. Dropping it would silently relocate a live run.
        os.environ.pop("WEINSTEIN_SCREENER_DATA_DIR", None)
        os.environ["SCREENER_DATA_DIR"] = _tmp("legacy")
        self.assertEqual(paths.data_file("x.pkl"), os.path.join(_tmp("legacy"), "x.pkl"))

    def test_a_per_file_override_beats_the_directory_one(self):
        os.environ["WEINSTEIN_SCREENER_DATA_DIR"] = _tmp("wsd")
        os.environ["SCREENER_BAR_CACHE"] = _tmp("just-this.pkl")
        self.assertEqual(paths.data_file("x.pkl", env="SCREENER_BAR_CACHE"),
                         _tmp("just-this.pkl"))

    def test_two_projects_do_not_share_a_directory(self):
        from market_core import paths as shared
        self.assertNotEqual(shared.data_dir("weinstein-screener"),
                            shared.data_dir("growth-screener"))
