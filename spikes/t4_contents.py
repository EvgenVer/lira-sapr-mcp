"""T4 probe: GetContents return types, document indexing, units, empty-table behaviour."""

from pathlib import Path

import pythoncom
import win32com.client
from win32com.client import gencache

pythoncom.CoInitialize()
app = gencache.EnsureDispatch("LiraSapr.Application")
c = win32com.client.constants
while app.DocumentCount:
    app.Document(0).Close()
doc = app.OpenDocument(str(Path("spikes/out/example01.lir").resolve()), False, True)
print("open returns:", type(doc), doc if isinstance(doc, tuple) else "")
doc = doc[0] if isinstance(doc, tuple) else doc
print("count", app.DocumentCount, "doc0", app.Document(0).Title, "active", app.ActiveDocument.PathName)


def tbl(kind):
    t = doc.AllTables.CreateNewItem(kind, None, c.kLiraModelPart_All, "x", -1)
    return win32com.client.CastTo(t, "ILiraTable")


t = tbl(c.kLiraTable_Nodes_Restraints)
for probe in ("", None, [], [[0]], ((None,),)):
    try:
        v = t.GetContents(probe)
        print(f"probe {probe!r}: {type(v).__name__} {v!r}"[:300])
    except Exception as e:
        print(f"probe {probe!r}: ERROR {e}")
t2 = doc.AllTables.CreateNewItem(c.kLiraTable_Nodes_Coordinates, [4, 5], c.kLiraModelPart_FromArray, "y", -1)
t2 = win32com.client.CastTo(t2, "ILiraTable")
print("from array:", repr(t2.GetContents("")))
u = app.MeasurementUnits
print("units geom", u.Geometry, "sections", u.Sections, "loads1", u.Loads1, "forces1", u.Forces1, "disp", u.Displacements)
new = app.CreateNewDocument("emptyprobe", c.kLiraModelType_5, "", c.kLiraLoadVaksType_Design)
for kind in (c.kLiraTable_Nodes_Coordinates, c.kLiraTable_Stiffnesses):
    try:
        tt = win32com.client.CastTo(new.AllTables.CreateNewItem(kind, None, c.kLiraModelPart_All, "z", -1), "ILiraTable")
        print("empty create ok", kind, repr(tt.GetContents("")))
    except Exception as e:
        print("empty", kind, "ERROR at", "create" if "tt" not in dir() else "get", e)
new.Close()
