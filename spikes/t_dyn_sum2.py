"""Probe: shape -1 (summary) of dynamic load case 4 of the analysed copy of example 04,
compared with the square root of the sum of squares of the stored shapes: forces of all
bars, displacements of all nodes. Run after t_dyn_sum.py."""

import math
import sys
from pathlib import Path

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.com.worker import ComWorker

sys.stdout.reconfigure(encoding="utf-8")
model = str(Path("spikes/out/tds/lmcp_tds.lir").resolve())
w = ComWorker()
a = ComLiraAdapter(pick_install(find_installs(), None))


def probe():
    r = a.results
    f = r._query(model, "kLiraRequest_LoadCaseForces", "ILiraLoadCaseForcesRequest",
                 "LoadCaseForces")  # fmt: skip
    worst, signs, n = 0.0, {"neg": 0, "pos": 0}, 0
    for el in range(1, 2000):
        try:
            if f.GetFamily(el) != 1:  # bars only
                continue
        except Exception:
            break
        for get in (f.GetBarN, f.GetBarMy, f.GetBarQz):
            shapes = [get(el, 1, 4, s, 0) for s in (1, 2, 3)]
            total = get(el, 1, 4, -1, 0)
            srss = math.sqrt(sum(v * v for v in shapes))
            worst = max(worst, abs(abs(total) - srss) / max(srss, 1e-6))
            signs["neg" if total < 0 else "pos"] += 1
            n += 1
    print(f"bars: {n} values, worst |summary| vs SRSS relative gap {worst:.2e}, signs {signs}")
    d = r._query(model, "kLiraRequest_LoadCaseDisplacement", "ILiraLoadCaseDisplacementsRequest",
                 "LoadCaseDisplacements")  # fmt: skip
    info = d.LoadCases.Item(3)
    print("disp case", info.Number, "shapes", info.DeformedShapes.AddToString())
    worst, n = 0.0, 0
    for node in range(1, 3000):
        try:
            shapes = [d.GetNodeZ(node, 4, s, 0) for s in (1, 5, 11)]
        except Exception:
            break
        for s in (-1, 0, 4, 14):
            try:
                total = d.GetNodeZ(node, 4, s, 0)
            except Exception:
                continue
            if node == 1:
                print("  node 1 shape", s, total, "shapes", shapes)
            if s == -1:
                srss = math.sqrt(sum(v * v for v in shapes))
                worst = max(worst, abs(abs(total) - srss) / max(srss, 1e-9))
                n += 1
    print(f"nodes: {n} values, worst |summary| vs SRSS relative gap {worst:.2e}")


w.call(a.connect, timeout=180)
w.call(probe, timeout=600)
