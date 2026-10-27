"""T2 spike, step 10: import a text export, save as .lir, so its tables can be dumped."""

import sys
from pathlib import Path

import pythoncom
from win32com.client import gencache

pythoncom.CoInitialize()
app = gencache.EnsureDispatch("LiraSapr.Application")
while app.DocumentCount:
    app.Document(0).Close()
src = Path(sys.argv[1]).resolve()
doc = app.ImportFile(str(src), "")
doc.SaveAs(str(src.with_suffix(".lir")), False)
print("saved", doc.PathName)
