"""ComLiraAdapter logic that does not need LIRA, on stand-ins for its COM objects."""

import pytest

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import LiraInstall
from lira_sapr_mcp.errors import LiraComError


class Doc:
    def __init__(self, path):
        self.PathName, self.Title, self.SystemLabel = path, "m", 5
        self.modified = False
        self.saves = 0
        self.closed = False

    def IsModified(self):
        return self.modified

    def Save(self, _ask):
        self.saves += 1
        self.modified = False

    def Close(self):
        self.closed = True

    def Activate(self):
        pass


class App:
    def __init__(self, doc):
        self.doc = doc
        self.ActiveDocument = doc
        self.DocumentCount = 1
        self.fail = False

    def Document(self, _i):
        return self.doc

    def StartAnalysis(self, _path):
        if self.fail:
            raise OSError("COM call failed")
        return True


@pytest.fixture
def lira(tmp_path):
    adapter = ComLiraAdapter(LiraInstall(2024, "LiraSapr.Application.2024", "", "2024 R2"))
    doc = Doc(str(tmp_path / "m.lir"))
    adapter._app = App(doc)
    return adapter, doc


def test_the_real_adapter_has_every_method_the_fake_one_has():
    import inspect

    from fakes import FakeAdapter

    fake = {n for n, _ in inspect.getmembers(FakeAdapter, inspect.isfunction)}
    real = {n for n, _ in inspect.getmembers(ComLiraAdapter, inspect.isfunction)}
    assert {n for n in fake if not n.startswith("_")} - real == set()


def read(adapter, doc):
    with adapter._reading(doc):
        doc.modified = True  # LIRA marks a document modified by a scratch table


def test_own_reads_do_not_count_as_changes(lira):
    adapter, doc = lira
    read(adapter, doc)
    assert not adapter.document_info().modified


def test_closing_a_read_model_saves_possible_owner_edits(lira):
    adapter, doc = lira
    read(adapter, doc)
    adapter.close_document(doc.PathName)
    assert doc.saves == 1 and doc.closed


def test_discarding_does_not_save(lira):
    adapter, doc = lira
    read(adapter, doc)
    adapter.close_document(doc.PathName, discard=True)
    assert doc.saves == 0 and doc.closed


def test_analysis_saves_a_read_model_first(lira):
    adapter, doc = lira
    read(adapter, doc)
    adapter.start_analysis(doc.PathName)
    assert doc.saves == 1
    assert adapter.analysis.status == "running"


def test_failed_start_does_not_leave_analysis_running(lira):
    adapter, doc = lira
    adapter._app.fail = True
    with pytest.raises(LiraComError):
        adapter.start_analysis(doc.PathName)
    assert adapter.analysis.status != "running"
