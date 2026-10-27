"""Probe: deformed shapes of dynamic load case 4 of example 04 (already analysed by t9_kinds)."""
from pathlib import Path

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.com.worker import ComWorker

model = str(Path("spikes/out/t9/lmcp_t9.lir").resolve())
w = ComWorker()
a = ComLiraAdapter(pick_install(find_installs(), None))


def probe():
    r = a.results
    resp = r._query(model, "kLiraRequest_LoadCaseDisplacement", "ILiraLoadCaseDisplacementsRequest",
                    "LoadCaseDisplacements", lambda q: q.Nodes.AddFromString("100"))
    lcs = resp.LoadCases
    for i in range(lcs.Count):
        it = lcs.Item(i)
        print("LC", it.Number, "shapes", it.DeformedShapes.AddToString(), "count", it.DeformedShapeCount,
              "modes", it.DynamicModeShapeCount, "summary", it.SummaryShapeCount)
    for shape in range(0, 6):
        try:
            print("disp LC4 shape", shape, resp.GetNodeX(100, 4, shape, 0), resp.GetNodeZ(100, 4, shape, 0))
        except Exception as e:
            print("disp LC4 shape", shape, "ERR", e)
    for summ in (0, 1):
        def fill(q, summ=summ):
            q.Elements.AddFromString("1 109")
            q.ForcesSum = summ
        f = r._query(model, "kLiraRequest_LoadCaseForces", "ILiraLoadCaseForcesRequest", "LoadCaseForces", fill)
        lc = [f.LoadCases.Item(i) for i in range(f.LoadCases.Count)]
        print("ForcesSum", summ, [(x.Number, x.DeformedShapeCount, x.SummaryShapeCount, x.DeformedShapes.AddToString()) for x in lc])
        for shape in range(0, 6):
            try:
                print("  N el1 LC4 shape", shape, f.GetBarN(1, 1, 4, shape, 0), "plate Mx", f.GetPlateMx(109, 1, 4, shape, 0))
            except Exception as e:
                print("  shape", shape, "ERR", e)
    p = r._query(model, "kLiraRequest_PeriodsOfVibrations", "ILiraPeriodsOfVibrationsRequest", "PeriodsOfVibrations")
    print("periods LCs", p.LoadCaseNumbers.AddToString())
    for name in ("GetPeriods", "GetFrequenciesHz", "GetModalMasses", "GetAccumulatedModalMasses", "GetParticipFactors", "GetDynamicLoadCaseType", "GetEigenvalues"):
        try:
            v = getattr(p, name)(4)
            print(name, type(v), v.AddToString() if hasattr(v, "AddToString") else v)
        except Exception as e:
            print(name, "ERR", e)


try:
    w.call(a.connect, timeout=180)
    w.call(probe, timeout=300)
finally:
    w.call(a.disconnect, timeout=30)
    w.stop()
