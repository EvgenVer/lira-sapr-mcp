"""Changing loads by rebuilding the model from text, on the in-memory adapter."""

import pytest

from fakes import FakeAdapter
from lira_sapr_mcp.adapters.base import TableError
from lira_sapr_mcp.errors import LiraError
from lira_sapr_mcp.services.loads import set_loads
from lira_sapr_mcp.services.textformat import Load

FRAME = """( 0/ 1; FRAME/ 2; 5/ 33; M 1 CM 100 T 1 C 1/ )
( 1/ 10 1 1 3/ 10 1 2 4/ 10 1 3 4/ )
( 4/ 0 0 0/ 6 0 0/ 0 0 3/ 6 0 3/ )
( 6/ 3 6 3 1 1/ 4 0 1 2 2/ )
( 7/ 1 10/ 2 5/ )
"""
TASK = "1. Основная задача"
CASES = [[1, "Dead", TASK, "Постоянное(П)", None], [2, "Wind", TASK, "Мгновенное(М)", None]]


@pytest.fixture
def model(tmp_path):
    adapter = FakeAdapter()
    path = tmp_path / "frame.lir"
    path.write_bytes(b"original")
    adapter.open_document(str(path))
    doc = adapter.docs[str(path)]
    doc["text"], doc["tables"]["LoadCases"] = FRAME, [list(r) for r in CASES]
    return adapter, path


def import_resets_kinds(adapter, kinds):
    """As LIRA 2024 R2: the rebuilt model gets the load case kinds of its default norms."""
    plain_import = adapter.import_file

    def import_file(path, template=""):
        info = plain_import(path, template)
        rows = [[*r[:3], kinds.get(r[0], r[3]), r[4]] for r in CASES]
        adapter.docs[info.path]["tables"]["LoadCases"] = rows
        return info

    adapter.import_file = import_file


def test_norms_reset_by_the_rebuild_are_refused_clearly(model):
    adapter, path = model
    import_resets_kinds(adapter, {2: "Особое ( Ps)"})

    with pytest.raises(LiraError, match="combination norms") as err:
        set_loads(adapter, str(path), [Load(1, 3, 6, 3, [12.5])], [1])

    assert "Мгновенное(М) -> Особое ( Ps)" in str(err.value)
    assert "original model is untouched" in str(err.value)
    assert path.read_bytes() == b"original"
    assert list(adapter.docs) == [str(path)]  # the rebuilt model was closed


def test_loads_change_and_lost_tables_come_back(model):
    adapter, path = model
    restraints = [[1, 1, 1, 1, 1, 1, 1, None]]
    adapter.docs[str(path)]["tables"]["Nodes_Restraints"] = restraints
    import_resets_kinds(adapter, {})  # the import loses Nodes_Restraints

    report = set_loads(adapter, str(path), [Load(1, 3, 6, 3, [12.5])], [1])

    assert report["loads_now"] == 2
    assert report["tables_restored_after_import"] == ["Nodes_Restraints"]
    assert adapter.read_table(str(path), "Nodes_Restraints") == restraints
    assert adapter.read_table(str(path), "LoadCases") == CASES


def test_a_table_that_cannot_be_restored_is_refused(model):
    adapter, path = model
    adapter.docs[str(path)]["tables"]["Nodes_Restraints"] = [[1, 1, None, None]]
    import_resets_kinds(adapter, {})
    adapter.write_table = lambda ref, name, rows, numbers=None: [TableError(0, 1, "bad")]

    with pytest.raises(LiraError, match="did not match") as err:
        set_loads(adapter, str(path), [Load(1, 3, 6, 3, [12.5])], [1])

    assert "Nodes_Restraints" in str(err.value)
    assert "original model is untouched" in str(err.value)
    assert path.read_bytes() == b"original"
    assert list(adapter.docs) == [str(path)]


def test_unreadable_load_cases_leave_the_kinds_to_the_full_check(model):
    adapter, path = model
    import_resets_kinds(adapter, {2: "Особое ( Ps)"})
    plain_read = adapter.read_table

    def read_table(ref, name, numbers=None):
        if name == "LoadCases":  # LIRA could not build the table for this model
            raise LiraError("cannot create table LoadCases")
        return plain_read(ref, name, numbers)

    adapter.read_table = read_table

    report = set_loads(adapter, str(path), [Load(1, 3, 6, 3, [12.5])], [1])

    assert report["loads_now"] == 2
