"""Run the shared package's own tests as part of this project's suite.

The shared code carries its own tests, and without this they run only if
somebody remembers to cd into the package. A regression there reaches
both projects and would be caught by neither — the same silent
propagation failure the drift check guards, pointing the other way.

unittest's discover refuses to walk outside the project root ("Path must
be within the project"), so the modules are loaded by path instead.
Absent checkout means skip, not fail: a machine running only an
installed wheel should not be blocked.
"""
import importlib.util
import os
import unittest

SHARED_TESTS = os.path.expanduser("~/market-data/market-core/tests")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_tests(loader, tests, pattern):
    if not os.path.isdir(SHARED_TESTS):
        return tests
    for entry in sorted(os.listdir(SHARED_TESTS)):
        if not (entry.startswith("test_") and entry.endswith(".py")):
            continue
        module = _load(os.path.join(SHARED_TESTS, entry), f"shared_{entry[:-3]}")
        tests.addTests(loader.loadTestsFromModule(module))
    return tests
