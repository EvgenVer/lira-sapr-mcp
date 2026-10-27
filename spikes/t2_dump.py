"""T2 spike, step 3: dump every input table of a model to learn the formats."""

import sys
from pathlib import Path

import pythoncom
import win32com.client
from win32com.client import gencache

model = Path(sys.argv[1]).resolve()
out = Path(__file__).parent / "out" / (model.stem + ".tables.txt")
pythoncom.CoInitialize()
app = gencache.EnsureDispatch("LiraSapr.Application")
c = win32com.client.constants
while app.DocumentCount:
    app.Document(0).Close()
doc = app.OpenDocument(str(model), False, True)
doc = doc[0] if isinstance(doc, tuple) else doc
names = {k for d in c.__dicts__ for k in d}
kinds = [k for k in names if k.startswith("kLiraTable_")]
with open(out, "w", encoding="utf-8") as f:
    for kind in sorted(kinds, key=lambda k: getattr(c, k)):
        if kind in ("kLiraTable_AllTables", "kLiraTable_Group", "kLiraTable_Cnt"):
            continue
        try:
            t = doc.AllTables.CreateNewItem(getattr(c, kind), None, c.kLiraModelPart_All, kind, -1)
            t = win32com.client.CastTo(t, "ILiraTable")
            data = t.GetContents("")
            lines = data.splitlines()
            print(f"== {kind} ({len(lines)} rows)", file=f)
            print("\n".join(lines[:12]), file=f)
        except Exception as e:
            print(
                f"== {kind}: ERROR {e.args[2][2] if len(e.args) > 2 and e.args[2] else e!r}", file=f
            )
print(out)
