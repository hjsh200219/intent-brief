import os
import sys

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "dev"))
import verify_docs  # noqa: E402


def test_docs_links_paths_versions():
    errors, _ = verify_docs.check()
    assert errors == []
