"""T2 spike, step 2: build a 6x3 m portal frame through input tables and read tables back."""

import sys
from pathlib import Path

import pythoncom
import win32com.client
from win32com.client import gencache

OUT = Path(__file__).parent / "out"
log = open(OUT / "t2_frame.log", "w", encoding="utf-8")


def p(*a):
    print(*a, file=log, flush=True)


pythoncom.CoInitialize()
app = gencache.EnsureDispatch("LiraSapr.Application")
c = win32com.client.constants
while app.DocumentCount:
    app.Document(0).Close()
doc = app.CreateNewDocument("t2frame", c.kLiraModelType_5, "T2 spike", c.kLiraLoadVaksType_Design)
tables = doc.AllTables


def table(kind, name):
    t = tables.CreateNewItem(getattr(c, kind), None, c.kLiraModelPart_All, name, -1)
    return win32com.client.CastTo(t, "ILiraTable")


def put(kind, rows):
    t = table(kind, kind)
    t.SetContents("\r\n".join("\t".join(map(str, r)) for r in rows))
    ok, errs = t.Apply()
    p(f"== apply {kind}: ok={ok} errs={errs!r}")
    return t


def show(kind):
    try:
        t = table(kind, kind)
        p(f"== {kind}:\n{t.GetContents('')}")
    except Exception as e:
        p(f"== {kind}: ERROR {e!r}")


put("kLiraTable_Nodes_Coordinates", [(1, 0, 0, 0), (2, 6, 0, 0), (3, 0, 0, 3), (4, 6, 0, 3)])
put("kLiraTable_Elements_TypeAndNodes", [(1, 10, "1, 3"), (2, 10, "2, 4"), (3, 10, "3, 4")])
for kind in sys.argv[1:] or [
    "kLiraTable_Nodes_Coordinates",
    "kLiraTable_Elements_TypeAndNodes",
    "kLiraTable_Nodes_Restraints",
    "kLiraTable_Stiffnesses",
    "kLiraTable_Elements_Stiffnesses",
    "kLiraTable_LoadCases",
    "kLiraTable_Bars_InternalForces",
    "kLiraTable_DCL",
]:
    show(kind)
doc.SaveAs(str((OUT / "t2frame.lir").resolve()), False)
p("saved:", doc.PathName)
