"""T2 spike, step 4: import a LIRA text-format file and dump its tables."""

import sys
from pathlib import Path

import pythoncom
import win32com.client
from win32com.client import gencache

src = Path(sys.argv[1]).resolve()
template = sys.argv[2] if len(sys.argv) > 2 else ""
out = Path(__file__).parent / "out" / (src.stem + ".import.txt")
pythoncom.CoInitialize()
app = gencache.EnsureDispatch("LiraSapr.Application")
c = win32com.client.constants
while app.DocumentCount:
    app.Document(0).Close()
with open(out, "w", encoding="utf-8") as f:
    try:
        doc = app.ImportFile(str(src), template)
        print("imported:", doc, file=f)
        print("title:", doc.Title, "path:", doc.PathName, "label:", doc.SystemLabel, file=f)
        for kind in (
            "kLiraTable_Nodes_Coordinates",
            "kLiraTable_Elements_TypeAndNodes",
            "kLiraTable_Nodes_Restraints",
            "kLiraTable_Stiffnesses",
            "kLiraTable_Elements_Stiffnesses",
            "kLiraTable_LoadCases",
        ):
            try:
                t = doc.AllTables.CreateNewItem(
                    getattr(c, kind), None, c.kLiraModelPart_All, kind, -1
                )
                t = win32com.client.CastTo(t, "ILiraTable")
                print(f"== {kind}\n{t.GetContents('')}", file=f)
            except Exception as e:
                print(f"== {kind}: ERROR {e!r}", file=f)
    except Exception as e:
        print("import ERROR:", repr(e), file=f)
print(out)
