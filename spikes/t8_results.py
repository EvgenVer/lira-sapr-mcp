"""T8 probe: empty node/element lists in result requests; response metadata."""

import pythoncom
import win32com.client
from win32com.client import gencache

pythoncom.CoInitialize()
gencache.EnsureModule("{BD6C09E6-B5EE-4DAB-8D61-C009BA755C46}", 0, 1, 0)
res = win32com.client.CastTo(win32com.client.Dispatch("{4F4546AE-AC54-48A2-9414-1B9EF6519A37}"), "ILiraResultsAccess")
c = win32com.client.constants
out = open("spikes/out/t8.log", "w", encoding="utf-8", buffering=1)
for name in ("t7good", "nosuchmodel"):
    try:
        req = win32com.client.CastTo(res.CreateNewRequest(c.kLiraRequest_LoadCaseDisplacement), "ILiraLoadCaseDisplacementsRequest")
        req.DocumentName = name
        r = res.LoadCaseDisplacements(req)
        print(name, "disp nodes:", r.NodeNumbers.AddToString(), "dirs:", r.Directions.AddToString(),
              "lcs:", r.LoadCases.Count, file=out)
        print("  node3 X Z UY:", r.GetNodeX(3, 1, 1, 0), r.GetNodeZ(3, 1, 1, 0), r.GetNodeUY(3, 1, 1, 0), file=out)
        req2 = win32com.client.CastTo(res.CreateNewRequest(c.kLiraRequest_LoadCaseForces), "ILiraLoadCaseForcesRequest")
        req2.DocumentName = name
        f = res.LoadCaseForces(req2)
        print("  forces: el1 sections", f.GetSectionCount(1), "el3 forces", f.GetForces(3).AddToString(), file=out)
        try:
            print("  el 99 sections", f.GetSectionCount(99), file=out)
        except Exception as e:
            print("  el 99 error", e.args[2][2] if e.args[2] else e, file=out)
        md = win32com.client.CastTo(res.CreateNewRequest(c.kLiraRequest_MainData), "ILiraMainDataRequest")
        md.DocumentName = name
        m = res.MainData(md)
        print("  main data:", [a for a in dir(m) if not a.startswith("_")][:40], file=out)
    except Exception as e:
        print(name, "ERROR", e, file=out)
