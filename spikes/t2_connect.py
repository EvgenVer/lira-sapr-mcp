"""T2 spike, step 1: connect to LIRA through COM and inspect an empty document."""

import pythoncom
import win32com.client
from win32com.client import gencache

pythoncom.CoInitialize()
app = gencache.EnsureDispatch("LiraSapr.Application")
print("documents open:", app.DocumentCount)
c = win32com.client.constants
doc = app.CreateNewDocument("t2frame", c.kLiraModelType_5, "T2 spike", c.kLiraLoadVaksType_Design)
print("doc:", doc.Title, doc.SystemLabel, doc.PathName)
tables = doc.AllTables
print("table items:", tables.ItemCount)
for name in (
    "kLiraTable_Nodes_Coordinates",
    "kLiraTable_Elements_TypeAndNodes",
    "kLiraTable_LoadCases",
    "kLiraTable_Stiffnesses",
    "kLiraTable_Nodes_Restraints",
):
    try:
        t = tables.CreateNewItem(getattr(c, name), None, c.kLiraModelPart_All, name, -1)
        t = win32com.client.CastTo(t, "ILiraTable")
        params = t.GetParameters()
        data = t.GetContents("")
        print(f"\n== {name}: params={params!r}\n{data!r}")
    except Exception as e:
        print(f"\n== {name}: ERROR {e!r}")
