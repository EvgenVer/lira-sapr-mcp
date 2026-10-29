"""Probe: summary (combined over modes) forces of a dynamic load case.

On a copy of example 04 (load case 4 is dynamic): turn on LIRA's CSV result tables
(SetGenerateCsvTables: forces, displacements), analyse, list the CSV files, and query
LiraResAPI with every combination of ForcesSum, shape number and history to find the
summary shape. Element 1 is a bar, 109 a plate.
"""

import shutil
import sys
import time
from pathlib import Path

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.com.worker import ComWorker

sys.stdout.reconfigure(encoding="utf-8")
MANUAL = Path(r"C:\Users\Public\Documents\LIRA SAPR\LIRA SAPR 2024\Manual\RU")
SRC = MANUAL / "04_пространственный каркас с фунд_плитой на упругом основании"
OUT = Path("spikes/out/tds").resolve()
OUT.mkdir(parents=True, exist_ok=True)
model = OUT / "lmcp_tds.lir"
shutil.copy(SRC / "04_3D каркас_упругое основание.lir", model)

w = ComWorker()
a = ComLiraAdapter(pick_install(find_installs(), None))


def run(fn, *args, timeout=600):
    return w.call(fn, *args, timeout=timeout)


def csv_on():
    doc = a.find_document(str(model))
    a._changed(doc)
    doc.SetGenerateCsvTables(True, [5, 6, 10])
    try:
        print("csv tables:", doc.GetGenerateCsvTables([]))
    except Exception as e:
        print("csv get ERR", str(e)[:80])
    doc.Save(False)


def probe():
    r = a.results
    for summ in (0, 1):
        for hist in (0, 1):

            def fill(q, summ=summ):
                q.Elements.AddFromString("1 109")
                q.ForcesSum = summ

            f = r._query(
                str(model),
                "kLiraRequest_LoadCaseForces",
                "ILiraLoadCaseForcesRequest",
                "LoadCaseForces",
                fill,
            )
            lc = [f.LoadCases.Item(i) for i in range(f.LoadCases.Count)]
            info = [
                (x.Number, x.DeformedShapeCount, x.DynamicModeShapeCount, x.SummaryShapeCount,
                 x.DeformedShapes.AddToString())
                for x in lc
            ]  # fmt: skip
            print(f"ForcesSum={summ} History={hist} cases {info}")
            for shape in [-1, 0, 1, 2, 3, 4, 5, 13, 14, 15, 100]:
                try:
                    v = (f.GetBarN(1, 1, 4, shape, hist), f.GetPlateMx(109, 1, 4, shape, hist))
                    print(f"   shape {shape}: bar N {v[0]:.4f}, plate Mx {v[1]:.4f}")
                except Exception as e:
                    print(f"   shape {shape}: ERR {str(e)[:80]}")


run(a.connect)
run(a.open_document, str(model))
run(csv_on)
work = Path(run(a.directories)["WorkDirectory"])
data = Path(run(a.directories)["DataDirectory"])
t0 = time.time()
run(a.start_analysis, str(model))
while run(a.analysis_status)["status"] == "running":
    time.sleep(1)
print("analysis:", run(a.analysis_status)["status"], f"{time.time() - t0:.0f} s")
for folder in {work, data, OUT}:
    for p in sorted(folder.glob("*")):
        if p.suffix.lower() == ".csv" and p.stat().st_mtime > t0 - 5:
            print("CSV", p, p.stat().st_size)
run(probe)
