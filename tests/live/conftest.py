"""Shared fixtures for tests against a real LIRA. Models live only in tests/live/_work."""

import shutil
from pathlib import Path

import pytest

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.com.worker import ComWorker

WORK = Path(__file__).parent / "_work"


@pytest.fixture(scope="session")
def worker():
    w = ComWorker()
    yield w
    w.stop()


@pytest.fixture(scope="session")
def adapter(worker):
    install = pick_install(find_installs(), None)
    if install is None:
        pytest.skip("no LIRA 2024+ installed")
    a = ComLiraAdapter(install)
    worker.call(a.connect, timeout=180)
    yield a
    worker.call(a.disconnect, timeout=30)


@pytest.fixture
def lira(worker, adapter):
    """Call adapter methods on the COM thread: ``lira(adapter.method, *args)``."""

    def run(fn, *args, **kwargs):
        return worker.call(fn, *args, timeout=180, **kwargs)

    # Close only what the test opened: the owner may have own models open in LIRA.
    before = {d.path.lower() for d in run(adapter.list_documents)}
    yield run
    for doc in run(adapter.list_documents):
        if doc.path.lower() not in before:
            run(adapter.close_document, doc.path or doc.title)


@pytest.fixture
def workdir(request):
    d = WORK / request.node.name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    return d
