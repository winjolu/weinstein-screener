"""Modules that are meant to be shared must actually be shared.

Written because they silently were not. A shim converting sharadar.py to
the shared implementation was applied, verified, and then destroyed by a
`git filter-repo` run that rewrote the working tree to match a rewritten
HEAD — discarding an uncommitted change. The commit that followed
described the sharing and contained only a requirements.txt line.

Nothing failed. The suite stayed green at 551, because the local copy
works perfectly well on its own. That is the whole problem: divergence
does not announce itself, it just quietly stops fixes from propagating.
Growth-screener spent that period without ema(), and this project spent
it without growth's stricter archival guard.

So the check is not "does it import" but "is this object the same object
the shared package exposes".
"""
import unittest

SHARED = (
    "sharadar", "costs", "stop_loss", "moving_averages", "mansfield_rs",
    "rate_limit", "sector_strength", "trend_support_resistance",
    "historical_levels", "neighbours",
)


class SharedModuleTest(unittest.TestCase):
    def test_every_shared_module_resolves_to_the_package(self):
        import importlib
        drifted = []
        for name in SHARED:
            local = importlib.import_module(f"screener.{name}")
            shared = importlib.import_module(f"market_core.{name}")
            if local is not shared:
                drifted.append(f"{name}: {getattr(local, '__file__', '?')}")
        self.assertEqual(
            drifted, [],
            "these have drifted back to a local copy, so fixes in the shared "
            "package will not reach them:\n  " + "\n  ".join(drifted))

    def test_a_shared_fix_is_visible_here(self):
        # ema() was added in this project and existed nowhere else until
        # the package was shared. Its presence proves the path is live
        # rather than merely importable.
        from screener import moving_averages
        self.assertTrue(hasattr(moving_averages, "ema"))

    def test_the_stricter_guard_from_the_sibling_project_arrived(self):
        # assert_writable refusing an unfrozen table came from the other
        # checkout. Finding it here proves propagation runs both ways.
        from screener import sharadar
        import inspect
        self.assertIn("unfrozen_ok", inspect.signature(sharadar.assert_writable).parameters)

    def test_the_reference_library_is_reachable(self):
        from market_core import reference
        self.assertTrue(reference.available(),
                        "the shared reference library is missing; "
                        "ln -s ~/market-data/reference reference")
