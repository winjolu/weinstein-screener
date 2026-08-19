"""Where this project writes things.

The logic lives in market_core.paths, shared so that every project
resolves locations the same way. Only the app name is local, which is
what keeps two projects from writing results into one file.

SCREENER_DB and SCREENER_DATA_DIR are honoured alongside the
WEINSTEIN_SCREENER_* names, because the shorter forms were already
documented and in use before the helper was shared.
"""
import os

from market_core import paths as _paths

APP = "weinstein-screener"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEGACY_DIR_ENV = ["SCREENER_DATA_DIR"]


def data_dir():
    return _paths.data_dir(APP, extra_env=LEGACY_DIR_ENV)


def data_file(name, env=None):
    return _paths.data_file(APP, name, env=env, extra_env=LEGACY_DIR_ENV)


def inside_checkout(path):
    return _paths.inside_checkout(path, REPO)
