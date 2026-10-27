import pytest

pytestmark = pytest.mark.lira

NODES = [[1, 0, 0, 0], [2, 6, 0, 0], [3, 0, 0, 3], [4, 6, 0, 3]]
ELEMENTS = [[1, 10, "1, 3"], [2, 10, "2, 4"], [3, 10, "3, 4"]]


def frame(lira, adapter):
    doc = lira(adapter.create_document, "frame", 5, "test frame")
    assert lira(adapter.write_table, doc.path, "Nodes_Coordinates", NODES) == []
    assert lira(adapter.write_table, doc.path, "Elements_TypeAndNodes", ELEMENTS) == []
    return doc


def table_count(lira, adapter, ref):
    return lira(lambda: adapter.find_document(ref).AllTables.ItemCount)


def test_capabilities_come_from_the_type_library(adapter):
    assert {"OpenDocument", "ImportFile", "StartAnalysis", "StartCmd"} <= adapter.capabilities
    assert {"Nodes_Coordinates", "ElevationMarks", "LoadCases"} <= set(adapter.table_kinds)


def test_create_save_reopen_round_trip(lira, adapter, workdir):
    doc = frame(lira, adapter)
    path = str(workdir / "frame.lir")
    saved = lira(adapter.save_document, doc.path, path)
    assert saved.saved and saved.path.lower() == path.lower()
    lira(adapter.close_document, path)
    info, _ = lira(adapter.open_document, path)
    assert info.title == "frame"
    assert lira(adapter.read_table, path, "Nodes_Coordinates") == NODES
    listed = {d.path.lower(): d for d in lira(adapter.list_documents)}
    assert listed[path.lower()].active


def test_scratch_tables_are_removed(lira, adapter):
    doc = frame(lira, adapter)
    lira(adapter.read_table, doc.path, "Elements_TypeAndNodes")
    assert table_count(lira, adapter, doc.path) == 0


def test_bad_rows_are_reported_and_not_applied(lira, adapter):
    doc = frame(lira, adapter)
    errors = lira(adapter.write_table, doc.path, "Elements_TypeAndNodes", [[1, 10, "1, 99"]])
    assert errors
    assert lira(adapter.read_table, doc.path, "Elements_TypeAndNodes") == ELEMENTS


def test_rows_for_selected_numbers_only(lira, adapter):
    doc = frame(lira, adapter)
    assert lira(adapter.read_table, doc.path, "Nodes_Coordinates", [2, 4]) == [NODES[1], NODES[3]]
    assert lira(adapter.write_table, doc.path, "Nodes_Coordinates", [[4, 6, 0, 4]], [4]) == []
    rows = lira(adapter.read_table, doc.path, "Nodes_Coordinates")
    assert rows == [*NODES[:3], [4, 6, 0, 4]]


def test_appending_a_row_adds_a_node(lira, adapter):
    doc = frame(lira, adapter)
    lira(adapter.write_table, doc.path, "Nodes_Coordinates", [*NODES, [5, 3, 0, 3]])
    assert len(lira(adapter.read_table, doc.path, "Nodes_Coordinates")) == 5


def test_units_are_named(lira, adapter):
    units = lira(adapter.units)
    assert units.geometry in {"m", "cm", "mm", "ft", "in"}
