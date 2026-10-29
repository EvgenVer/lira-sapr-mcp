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
# Kinds as LIRA's default norms (SP 20.13330) name them, and what LIRA turns a SNiP
# 2.01.07-85* kind into when it is written into a model with those norms.
SP20 = {"Постоянное ( P)", "Кратк. доминир.1 ( Pt1)", "Мгновенное(М)", "Неактивное (Н/а)"}
SNIP_IN_SP20 = {"Постоянное(П)": "Постоянное ( P)", "Длительное(Д)": "Постоянное ( P)"}


@pytest.fixture
def model(tmp_path):
    adapter = FakeAdapter()
    path = tmp_path / "frame.lir"
    path.write_bytes(b"original")
    adapter.open_document(str(path))
    doc = adapter.docs[str(path)]
    doc["text"], doc["tables"]["LoadCases"] = FRAME, [list(r) for r in CASES]
    return adapter, path


def import_resets_kinds(adapter, kinds, cases=CASES):
    """As LIRA 2024 R2: the rebuilt model gets the default norms, so the import scrambles
    load case kinds, and a written kind is mapped into the default norms' dictionary."""
    plain_import, plain_write = adapter.import_file, adapter.write_table

    def import_file(path, template=""):
        info = plain_import(path, template)
        rows = [[*r[:3], kinds.get(r[0], r[3]), r[4]] for r in cases]
        adapter.docs[info.path]["tables"]["LoadCases"] = rows
        return info

    def write_table(ref, name, rows, numbers=None):
        if name == "LoadCases":
            rows = [[*r[:3], r[3] if r[3] in SP20 else SNIP_IN_SP20[r[3]], *r[4:]] for r in rows]
        return plain_write(ref, name, rows, numbers)

    adapter.import_file, adapter.write_table = import_file, write_table


def test_other_norms_lost_in_the_rebuild_are_refused_clearly(model):
    adapter, path = model
    cases = [[1, "Dead", TASK, "Постоянное(П)", None], [2, "Live", TASK, "Длительное(Д)", None]]
    adapter.docs[str(path)]["tables"]["LoadCases"] = cases
    import_resets_kinds(adapter, {1: "Постоянное ( P)", 2: "Длит. доминир.1 ( Pl1)"}, cases)

    with pytest.raises(LiraError, match="combination norms") as err:
        set_loads(adapter, str(path), [Load(1, 3, 6, 3, [12.5])], [1])

    assert "2: Длительное(Д) -> Постоянное ( P)" in str(err.value)
    assert "original model is untouched" in str(err.value)
    assert path.read_bytes() == b"original"
    assert list(adapter.docs) == [str(path)]  # the rebuilt model was closed


def test_default_norms_kinds_scrambled_by_the_import_are_restored(model):
    adapter, path = model
    cases = [
        [1, "Dead", TASK, "Постоянное ( P)", None],
        [2, "Snow", TASK, "Кратк. доминир.1 ( Pt1)", None],
        [3, "Wind", TASK, "Мгновенное(М)", None],
    ]
    adapter.docs[str(path)]["tables"]["LoadCases"] = cases
    import_resets_kinds(adapter, {2: "Длит. прочие ( Pl)", 3: "Особое ( Ps)"}, cases)

    report = set_loads(adapter, str(path), [Load(1, 3, 6, 3, [12.5])], [1])

    assert report["tables_restored_after_import"] == ["LoadCases"]
    assert adapter.read_table(str(path), "LoadCases") == cases


def test_loads_change_and_lost_tables_come_back(model):
    adapter, path = model
    restraints = [[1, 1, 1, 1, 1, 1, 1, None]]
    adapter.docs[str(path)]["tables"]["Nodes_Restraints"] = restraints
    cases = [[1, "Dead", TASK, "Постоянное ( P)", None]]
    adapter.docs[str(path)]["tables"]["LoadCases"] = [list(r) for r in cases]
    import_resets_kinds(adapter, {}, cases)  # the import loses Nodes_Restraints

    report = set_loads(adapter, str(path), [Load(1, 3, 6, 3, [12.5])], [1])

    assert report["loads_now"] == 2
    assert report["tables_restored_after_import"] == ["Nodes_Restraints"]
    assert adapter.read_table(str(path), "Nodes_Restraints") == restraints
    assert adapter.read_table(str(path), "LoadCases") == cases


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


def test_a_table_lira_refuses_to_take_is_refused_plainly(model):
    """As a model with construction stages: LIRA's Apply of LoadCases fails outright."""
    adapter, path = model
    import_resets_kinds(adapter, {1: None, 2: None})
    plain_write = adapter.write_table

    def write_table(ref, name, rows, numbers=None):
        if name == "LoadCases":
            raise LiraError("apply table LoadCases failed: Ошибка.")
        return plain_write(ref, name, rows, numbers)

    adapter.write_table = write_table

    with pytest.raises(LiraError, match="did not match") as err:
        set_loads(adapter, str(path), [Load(1, 3, 6, 3, [12.5])], [1])

    assert "apply table LoadCases failed" in str(err.value)
    assert "combination norms" not in str(err.value)
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
