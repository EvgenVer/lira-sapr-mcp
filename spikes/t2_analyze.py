"""T2 spike, step 5: import the frame, save, run analysis waiting for COM events, read forces."""

import sys
import time
from pathlib import Path

import pythoncom
import win32com.client
from win32com.client import gencache

OUT = Path(__file__).parent / "out"
log = open(OUT / "t2_analyze.log", "w", encoding="utf-8")


def p(*a):
    print(*a, file=log, flush=True)


class AppEvents:
    finished = None
    stages = []

    def OnAnalysisStarting(self, Stage):
        AppEvents.stages.append(Stage)
        p("event AnalysisStarting", Stage)

    def OnAnalysisFinished(self, FinishCode):
        AppEvents.finished = FinishCode
        p("event AnalysisFinished", FinishCode)

    def OnAnalysisStopped(self, StopCode):
        AppEvents.finished = ("stopped", StopCode)
        p("event AnalysisStopped", StopCode)


pythoncom.CoInitialize()
app = gencache.EnsureDispatch("LiraSapr.Application")
win32com.client.WithEvents(app, AppEvents)
c = win32com.client.constants
while app.DocumentCount:
    app.Document(0).Close()

src = Path(sys.argv[1]).resolve()
doc = app.ImportFile(str(src), "")
sec = doc.AllTables.CreateNewItem(
    c.kLiraTable_Elements_DesignSectionsCount, None, c.kLiraModelPart_All, "sections", -1
)
sec = win32com.client.CastTo(sec, "ILiraTable")
sec.SetContents([[1, 3], [2, 3], [3, 3]])
p("design sections apply:", sec.Apply())
lir = OUT / (src.stem + ".lir")
doc.SaveAs(str(lir.resolve()), False)
p("saved", doc.PathName)

t0 = time.time()
ok = app.StartAnalysis(str(lir.resolve()))
p("StartAnalysis ->", ok)
while AppEvents.finished is None and time.time() - t0 < 300:
    pythoncom.PumpWaitingMessages()
    time.sleep(0.05)
p(f"finished={AppEvents.finished} after {time.time() - t0:.1f}s, stages={AppEvents.stages}")

gencache.EnsureModule("{BD6C09E6-B5EE-4DAB-8D61-C009BA755C46}", 0, 1, 0)
res = win32com.client.Dispatch("{4F4546AE-AC54-48A2-9414-1B9EF6519A37}")
res = win32com.client.CastTo(res, "ILiraResultsAccess")
rc = win32com.client.constants
req = res.CreateNewRequest(rc.kLiraRequest_LoadCaseForces)
req = win32com.client.CastTo(req, "ILiraLoadCaseForcesRequest")
req.DocumentName = src.stem
req.Elements.AddFromString("1-3")
resp = res.LoadCaseForces(req)
for el in (1, 2, 3):
    n = resp.GetSectionCount(el)
    row = []
    for cs in range(1, n + 1):
        row.append(
            f"cs{cs}: N={resp.GetBarN(el, cs, 1, 1, 0):.3f} "
            f"My={resp.GetBarMy(el, cs, 1, 1, 0):.3f} Qz={resp.GetBarQz(el, cs, 1, 1, 0):.3f}"
        )
    p(f"element {el} ({n} sections): " + " | ".join(row))
