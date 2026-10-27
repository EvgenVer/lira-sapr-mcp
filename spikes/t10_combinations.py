"""Probe: load combinations (DCL) and design combinations (DCF) on LIRA examples 01 and 04."""

import shutil
import time
from pathlib import Path

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.com.worker import ComWorker

MANUAL = Path(r"C:\Users\Public\Documents\LIRA SAPR\LIRA SAPR 2024\Manual\RU")
OUT = Path("spikes/out/t10").resolve()
OUT.mkdir(parents=True, exist_ok=True)
m01 = OUT / "lmcp_t10_01.lir"
shutil.copy(MANUAL / "01_плоская рама ЖБ" / "01_2D рама ЖБ.lir", m01)
m04 = Path("spikes/out/t9/lmcp_t9.lir").resolve()

w = ComWorker()
a = ComLiraAdapter(pick_install(find_installs(), None))


def analyse(path):
    a.open_document(str(path))
    a.start_analysis(str(path))


def wait():
    # Poll from this thread: the COM thread must stay free to pump LIRA's events.
    t = time.time()
    while time.time() - t < 600:
        st = w.call(a.analysis_status, timeout=30)
        if st["status"] != "running":
            return st
        time.sleep(1)
    return st


def probe(path):
    r = a.results
    print("==", path.name)
    try:
        dcl = r._query(str(path), "kLiraRequest_LoadCombinationForces",
                       "ILiraLoadCombinationForcesRequest", "LoadCombinationForces",
                       lambda q: q.Elements.AddFromString("1"))
        infos = dcl.LoadCombinations
        print("DCL count", infos.Count, "code", infos.Code, "normative", infos.IsNormativeLoads)
        for i in range(infos.Count):
            it = infos.Item(i)
            print("  DCL", it.Number, repr(it.Name), "formula", it.FormulaNumber, "use",
                  it.LoadCombinationUsed, "special", it.IsSpecial, "seismic", it.IsSeismic)
        if infos.Count:
            n = infos.Item(0).Number
            print("  forces el1", dcl.GetForces(1).AddToString(), "sections", dcl.GetSectionCount(1))
            for ls in (1, 2, 3, 4):
                try:
                    print("  LS", ls, "N", dcl.GetBarN(1, 1, n, ls), "My", dcl.GetBarMy(1, 1, n, ls))
                except Exception as e:
                    print("  LS", ls, "ERR", e)
            d = r._query(str(path), "kLiraRequest_LoadCombinationDisplacements",
                         "ILiraLoadCombinationDisplacementsRequest",
                         "LoadCombinationDisplacements", lambda q: q.Nodes.AddFromString("2"))
            print("  disp node2 DCL", n, d.GetNodeX(2, n), d.GetNodeZ(2, n), d.Directions.AddToString())
    except Exception as e:
        print("DCL ERR", e, e.__cause__)
    try:
        dcf = r._query(str(path), "kLiraRequest_DesignCombinationForces",
                       "ILiraDesignCombinationForcesRequest", "DesignCombinationForces",
                       lambda q: q.Elements.AddFromString("1"))
        print("DCF forces el1", dcf.GetForces(1).AddToString(), "sections", dcf.GetSectionCount(1))
        for ls in (1, 2, 3, 4):
            try:
                cnt = dcf.GetDCLCount(1, 1, ls)
                print(" LS", ls, "count", cnt)
                for k in range(1, min(cnt, 4) + 1):
                    print("   #", k, "N", dcf.GetBarN(1, 1, ls, k), "My", dcf.GetBarMy(1, 1, ls, k),
                          "crit", dcf.GetCriterionNumber(1, 1, ls, k), "col",
                          dcf.GetColumnNumber(1, 1, ls, k), "group", dcf.GetInternalGroup(1, 1, ls, k),
                          "flag", dcf.GetCraneEarthquakeFlag(1, 1, ls, k), "cases",
                          dcf.GetLoadCases(1, 1, ls, k).AddToString())
            except Exception as e:
                print(" LS", ls, "ERR", e)
    except Exception as e:
        print("DCF ERR", e, e.__cause__)


try:
    w.call(a.connect, timeout=180)
    w.call(analyse, m01, timeout=120)
    st = wait()
    print("01:", st["status"], st.get("protocol", {}).get("clean"), st.get("stages"))
    w.call(probe, m01, timeout=300)
    w.call(probe, m04, timeout=300)
finally:
    w.call(a.disconnect, timeout=30)
    w.stop()
