"""T14 probe: does Stiffnesses_Factors change displacements? Reads the example 3 test model."""

from pathlib import Path

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install

MODEL = (
    Path(__file__).parents[1]
    / "tests/live/_work/test_stiffer_group_moves_less/lmcp_edit.lir"
).resolve()

adapter = ComLiraAdapter(pick_install(find_installs(), None))
adapter.connect()
try:
    for row in adapter.node_displacements(str(MODEL), [3, 4], None):
        print(row)
    info, _ = adapter.open_document(str(MODEL))
    for table in ("Stiffnesses_Factors", "Elements_Stiffnesses", "Stiffnesses"):
        print(table, adapter.read_table(info.path, table))
    adapter.close_document(info.path, True)
finally:
    adapter.disconnect()
