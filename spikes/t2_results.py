"""T2 spike, step 6: probe result indexing (sections and load cases)."""

import sys
from pathlib import Path

import pythoncom
import win32com.client
from win32com.client import gencache

OUT = Path(__file__).parent / "out"
log = open(OUT / "t2_results.log", "w", encoding="utf-8")


def p(*a):
    print(*a, file=log, flush=True)


pythoncom.CoInitialize()
gencache.EnsureModule("{BD6C09E6-B5EE-4DAB-8D61-C009BA755C46}", 0, 1, 0)
res = win32com.client.CastTo(
    win32com.client.Dispatch("{4F4546AE-AC54-48A2-9414-1B9EF6519A37}"), "ILiraResultsAccess"
)
rc = win32com.client.constants
req = win32com.client.CastTo(
    res.CreateNewRequest(rc.kLiraRequest_LoadCaseForces), "ILiraLoadCaseForcesRequest"
)
req.DocumentName = sys.argv[1]
req.Elements.AddFromString("1-3")
resp = res.LoadCaseForces(req)
lcs = resp.LoadCases
p("load cases in response:", lcs.Count if hasattr(lcs, "Count") else lcs)
for el in (1, 2, 3):
    p(
        f"element {el}: sections={resp.GetSectionCount(el)} family={resp.GetFamily(el)} "
        f"type={resp.GetType(el)} forces={resp.GetForces(el).AddToString()}"
    )
info = lcs.Item(0) if lcs.Count else None
if info:
    p("lc info:", info.Number, info.DeformedShapeCount, info.DeformedShapes.AddToString())
for cs in (0, 1, 2):
    for lc in (0, 1):
        for shape in (0, 1):
            for hist in (0, 1, -1):
                try:
                    v = resp.GetBarMy(3, cs, lc, shape, hist)
                    p(f"cs={cs} lc={lc} shape={shape} hist={hist}: My={v:.3f}")
                except Exception:
                    pass
