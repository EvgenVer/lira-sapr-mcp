"""T2 spike, step 9: run menu command 'Create text file' (5049) on an opened model."""

import sys
import time
from pathlib import Path

import pythoncom
from win32com.client import gencache

pythoncom.CoInitialize()
app = gencache.EnsureDispatch("LiraSapr.Application")
while app.DocumentCount:
    app.Document(0).Close()
src = Path(sys.argv[1]).resolve()
doc = app.OpenDocument(str(src), False, True)
doc = doc[0] if isinstance(doc, tuple) else doc
doc.Activate()
t0 = time.time()
print("StartCmd 5049 ...", flush=True)
app.StartCmd(5049)
print(f"StartCmd returned after {time.time() - t0:.1f}s", flush=True)
