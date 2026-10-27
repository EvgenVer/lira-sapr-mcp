"""T2 spike, step 7: can SaveAs write the LIRA text format (to read and edit loads)?"""

import sys
from pathlib import Path

import pythoncom
from win32com.client import gencache

OUT = Path(__file__).parent / "out"
pythoncom.CoInitialize()
app = gencache.EnsureDispatch("LiraSapr.Application")
while app.DocumentCount:
    app.Document(0).Close()
src = Path(sys.argv[1]).resolve()
doc = app.OpenDocument(str(src), False, True)
doc = doc[0] if isinstance(doc, tuple) else doc
target = OUT / (src.stem + "_export.txt")
try:
    doc.SaveAs(str(target.resolve()), False)
    print("SaveAs ok, doc path now:", doc.PathName)
except Exception as e:
    print("SaveAs error:", e)
print("exists:", target.exists(), target.stat().st_size if target.exists() else "")
