"""Probe: result kinds on LIRA example 04 (frame + slab on elastic base), analysed copy."""
import shutil
import sys
import time
from pathlib import Path

import win32com.client

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.com.worker import ComWorker

SRC = Path(r"C:\Users\Public\Documents\LIRA SAPR\LIRA SAPR 2024\Manual\RU")
SRC = SRC / "04_пространственный каркас с фунд_плитой на упругом основании"
SRC = SRC / "04_3D каркас_упругое основание.lir"
work = Path("spikes/out/t9").resolve()
work.mkdir(parents=True, exist_ok=True)
model = work / "lmcp_t9.lir"
shutil.copy(SRC, model)

w = ComWorker()
a = ComLiraAdapter(pick_install(find_installs(), None))


def analyse():
    a.open_document(str(model))
    a.start_analysis(str(model))


def probe():
    r = a.results
    c = win32com.client
    main = r._query(str(model), "kLiraRequest_MainData", "ILiraMainDataRequest", "MainData")
    print("nodes", main.GetNodeCount(), "elements", main.GetElementCount(), "dcl", main.GetDCLCount() if hasattr(main, "GetDCLCount") else "?")
    n = main.GetElementCount()
    resp = r._query(str(model), "kLiraRequest_LoadCaseForces", "ILiraLoadCaseForcesRequest",
                    "LoadCaseForces", lambda q: q.Elements.AddFromString(f"1-{n}"))
    fams = {}
    for el in range(1, n + 1):
        f = resp.GetFamily(el)
        if f not in fams:
            fams[f] = (el, resp.GetForces(el).AddToString(), resp.GetSectionCount(el))
    print("families", fams)
    lcs = resp.LoadCases
    for i in range(lcs.Count):
        it = lcs.Item(i)
        print("LC", it.Number, "shapes", it.DeformedShapeCount, "modes", it.DynamicModeShapeCount,
              "summary", it.SummaryShapeCount)
    for kind, iface, meth in [
        ("kLiraRequest_LoadCombinationForces", "ILiraLoadCombinationForcesRequest", "LoadCombinationForces"),
        ("kLiraRequest_DesignCombinationForces", "ILiraDesignCombinationForcesRequest", "DesignCombinationForces"),
        ("kLiraRequest_PeriodsOfVibrations", "ILiraPeriodsOfVibrationsRequest", "PeriodsOfVibrations"),
        ("kLiraRequest_SelectedReinforcement", "ILiraSelectedReinforcementRequest", "SelectedReinforcement"),
    ]:
        try:
            fill = (lambda q: q.Elements.AddFromString("1-5")) if "Elements" in dir(c.CastTo(r._access().CreateNewRequest(getattr(r._c, kind)), iface)) else None
            x = r._query(str(model), kind, iface, meth, fill)
            print(kind, "OK", [m for m in dir(x) if not m.startswith("_")][:40])
        except Exception as e:
            print(kind, "FAIL", e, getattr(e, "__cause__", None))


try:
    w.call(a.connect, timeout=180)
    w.call(analyse, timeout=120)
    t = time.time()
    while time.time() - t < 600:
        st = w.call(a.analysis_status, timeout=30)
        if st["status"] != "running":
            break
        time.sleep(1)
    print(st["status"], st.get("protocol", {}).get("verdict"), time.time() - t)
    w.call(probe, timeout=300)
finally:
    w.call(a.disconnect, timeout=30)
    w.stop()
