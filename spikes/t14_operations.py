"""T14 probe: high-level edits through input tables, and self weight, on a copy of the frame.

Works only on spikes/out/t14_frame.lir (made from the text format here).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tests" / "live"))

from test_live_loads import FRAME  # noqa: E402

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter  # noqa: E402
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install  # noqa: E402
from lira_sapr_mcp.services import loads  # noqa: E402

OUT = Path(__file__).parent / "out"
MODEL = OUT / "t14_frame.lir"


def show(adapter, ref, *tables):
    for t in tables:
        print(f"  {t}: {adapter.read_table(ref, t)}")


adapter = ComLiraAdapter(pick_install(find_installs(), None))
adapter.connect()
try:
    for d in adapter.list_documents():
        if d.title == "t14_frame":
            adapter.close_document(d.path or d.title, True)
    info = loads.import_text_model(adapter, FRAME, str(MODEL))
    ref = info.path
    print("1. as imported")
    show(adapter, ref, "Nodes_Coordinates", "Elements_TypeAndNodes", "Stiffnesses",
         "Elements_Stiffnesses", "Nodes_Restraints", "Stiffnesses_Factors", "LoadCases")

    print("2. add node 5 by numbers=[5]")
    print("  errors:", adapter.write_table(ref, "Nodes_Coordinates", [[5, 3.0, 0.0, 6.0]], [5]))
    show(adapter, ref, "Nodes_Coordinates")

    print("3. add node 6 by appending to the whole table")
    rows = adapter.read_table(ref, "Nodes_Coordinates") + [[6, 9.0, 0.0, 3.0]]
    print("  errors:", adapter.write_table(ref, "Nodes_Coordinates", rows))
    show(adapter, ref, "Nodes_Coordinates")

    print("4. add element 4 (4 -> 6) by numbers=[4]")
    print("  errors:", adapter.write_table(ref, "Elements_TypeAndNodes", [[4, 10, "4, 6"]], [4]))
    show(adapter, ref, "Elements_TypeAndNodes", "Elements_Stiffnesses")

    print("5. restraint node 6 fixed by numbers=[6]")
    row = [6, 1, 1, 1, 1, 1, 1, None]
    print("  errors:", adapter.write_table(ref, "Nodes_Restraints", [row], [6]))
    show(adapter, ref, "Nodes_Restraints")

    print("6. new stiffness 2 by copying row 1 with B:80")
    st = adapter.read_table(ref, "Stiffnesses")
    new = list(st[0])
    new[0] = 2
    new[4] = str(new[4]).replace("B:40", "B:80")
    print("  errors:", adapter.write_table(ref, "Stiffnesses", st + [new]))
    show(adapter, ref, "Stiffnesses")

    print("7. element 4 gets stiffness 2; factor 2.0 for elements 1, 2")
    print("  errors:", adapter.write_table(ref, "Elements_Stiffnesses", [[4, 2]], [4]))
    print("  errors:", adapter.write_table(ref, "Stiffnesses_Factors", [[1, 2.0], [2, 2.0]], [1, 2]))
    show(adapter, ref, "Elements_Stiffnesses", "Stiffnesses_Factors")

    print("8. self weight into load case 2")
    doc = adapter.find_document(ref)
    print("  current load case:", doc.CurrentLoadCase)
    doc.CurrentLoadCase = 2
    print("  message:", repr(doc.SetDeadWeightLoad(32, 1.1)))
    show(adapter, ref, "LoadCases")
    text = adapter.export_text(ref)
    for line in text.splitlines():
        if line.lstrip().startswith(("( 6/", "( 7/")):
            print("  ", line[:300])
    adapter.save_document(ref)
    print("saved", MODEL)
finally:
    adapter.disconnect()
