"""Shared-package integrity, collected from the shared package itself.

The check lives in market_core.integrity so that every project runs the
same one. A drift detector owned by a single checkout is the mistake it
exists to catch — which is how both the Sharadar client and the path
helper came to exist twice.

Importing the case is the whole file. unittest collects it from this
module's namespace.
"""
from market_core.integrity import SharedPackageTestCase  # noqa: F401


class ThisProjectUsesTheSharedPackage(SharedPackageTestCase):
    package = "screener"
