"""Nothing committed may depend on where this happens to be checked out.

Absolute paths are the usual culprit. A cache pinned to a directory that
exists on one machine passes there and fails everywhere else, and the
failure is confusing rather than obvious: the test does not report a
missing file, it reports whatever the code does with an empty result.

The two data-agreement tests both did this. They now read a location
from the environment and skip when it is unset, which is the behaviour
that makes them safe to run anywhere.
"""
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELF = "tests/test_portability.py"

# A quoted path rooted at the filesystem. Matched inside quotes so that
# prose in a docstring or comment mentioning a directory does not fail.
ABSOLUTE_PATH = re.compile(r'''["'](/(private|Users|home|var|opt|tmp)/)''')

SKIP_SUFFIXES = (".json", ".pyc", ".pine", ".md")


def _tracked():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                         capture_output=True, text=True)
    return [f for f in out.stdout.split("\0") if f] if out.returncode == 0 else []


@unittest.skipUnless(os.path.isdir(os.path.join(ROOT, ".git")), "not a git checkout")
class PortabilityTest(unittest.TestCase):
    def test_no_tracked_source_hardcodes_an_absolute_path(self):
        bad = []
        for rel in _tracked():
            if rel == SELF or rel.endswith(SKIP_SUFFIXES):
                continue
            try:
                with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except (IsADirectoryError, FileNotFoundError):
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if ABSOLUTE_PATH.search(line):
                    bad.append(f"{rel}:{number}: {line.strip()[:80]}")
        self.assertEqual(bad, [],
                         "hardcoded absolute path:\n  " + "\n  ".join(bad))

    def test_the_optional_data_caches_are_configurable(self):
        # Both read an environment variable with a home-relative default,
        # so a machine without the cache skips rather than fails.
        for module, name in (("tests.test_data_agreement", "SHARADAR_CACHE"),
                             ("tests.test_adjustment_integrity", "CACHE")):
            mod = __import__(module, fromlist=[name])
            value = getattr(mod, name)
            self.assertFalse(value.startswith("/private"),
                             f"{module}.{name} is pinned to a scratch directory")
