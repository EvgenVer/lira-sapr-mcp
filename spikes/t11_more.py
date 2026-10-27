"""Probe: periods, selected reinforcement, loads on fragment and punching (examples 01, 02, 04)."""

import shutil
import time
from pathlib import Path

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.com.worker import ComWorker

MANUAL = Path(r"C:\Users\Public\Documents\LIRA SAPR\LIRA SAPR 2024\Manual\RU")
OUT = Path("spikes/out/t11").resolve()
OUT.mkdir(parents=True, exist_ok=True)
m02 = OUT / "lmcp_t11_02.lir"
shutil.copy(MANUAL / "02_плита ЖБ" / "02_плита ЖБ.lir", m02)
m01 = Path("spikes/out/t10/lmcp_t10_01.lir").resolve()
m04 = Path("spikes/out/t9/lmcp_t9.lir").resolve()

w = ComWorker()
a = ComLiraAdapter(pick_install(find_installs(), None))


def wait():
    t = time.time()
    while time.time() - t < 600:
        st = w.call(a.analysis_status, timeout=30)
        if st["status"] != "running":
            return st
        time.sleep(1)
    return st


def q(path, kind, iface, method, fill=None):
    return a.results._query(str(path), kind, iface, method, fill)


def reinforcement(path, elements):
    print("== reinforcement", path.name)
    try:
        r = q(path, "kLiraRequest_SelectedReinforcement", "ILiraSelectedReinforcementRequest",
              "SelectedReinforcement", lambda x: x.Elements.AddFromString(elements))
        for el in map(int, elements.split()):
            fam = r.GetFamily(el)
            print(" el", el, "family", fam, "sections", r.GetSectionCount(el))
            if fam == 1:
                for sym in (0, 1):
                    for stage in (0, 1):
                        try:
                            print("   sym", sym, "stage", stage, "AU1", r.GetBarAU1(el, 1, 1, sym, stage),
                                  "AS1", r.GetBarAS1(el, 1, 1, sym, stage),
                                  "PERC", r.GetBarPERC(el, 1, 1, sym, stage),
                                  "crack", r.GetBarCrackSHORT(el, 1, sym, stage))
                        except Exception as e:
                            print("   sym", sym, "stage", stage, "ERR", e)
            elif fam == 2:
                for stage in (0, 1):
                    try:
                        print("   stage", stage, "AS1", r.GetPlateAS1(el, 1, stage),
                              "AS3", r.GetPlateAS3(el, 1, stage), "percX", r.GetPlatePercX(el, stage),
                              "crack", r.GetPlateCrackSHORT(el, stage))
                    except Exception as e:
                        print("   stage", stage, "ERR", e)
    except Exception as e:
        print(" ERR", e, e.__cause__)


def nodal(path, nodes):
    print("== fragment/punch", path.name)
    for kind, iface, meth, names in (
        ("kLiraRequest_FragmLoadForces", "ILiraFragmLoadsRequest", "FragmLoads", ("RX", "RZ", "RUY")),
        ("kLiraRequest_PunchLoadForces", "ILiraPunchLoadsRequest", "PunchLoads", ("N", "MX", "QX")),
    ):
        try:
            r = q(path, kind, iface, meth, lambda x: x.Nodes.AddFromString(nodes))
            print(" ", meth, "nodes", r.NodeNumbers.AddToString(), "forces", r.Forces.AddToString(),
                  "cases", r.LoadCases.Count)
            for n in r.NodeNumbers.AddToString().replace(",", " ").split()[:3]:
                if "-" in n:
                    n = n.split("-")[0]
                print("   node", n, [getattr(r, "GetNode" + c)(int(n), 1, 1) for c in names])
        except Exception as e:
            print(" ", meth, "ERR", e, e.__cause__)


def periods(path):
    print("== periods", path.name)
    try:
        r = q(path, "kLiraRequest_PeriodsOfVibrations", "ILiraPeriodsOfVibrationsRequest",
              "PeriodsOfVibrations")
        print(" cases", r.LoadCaseNumbers.AddToString())
    except Exception as e:
        print(" ERR", e, e.__cause__)


try:
    w.call(a.connect, timeout=180)
    w.call(a.open_document, str(m02), timeout=120)
    w.call(a.start_analysis, str(m02), timeout=120)
    st = wait()
    print("02:", st["status"], st.get("protocol", {}).get("clean"), st.get("stages"))
    w.call(reinforcement, m01, "1 2 3", timeout=300)
    w.call(reinforcement, m02, "1 2", timeout=300)
    w.call(reinforcement, m04, "1 109", timeout=300)
    w.call(nodal, m02, "1-5", timeout=300)
    w.call(nodal, m04, "1-5", timeout=300)
    w.call(periods, m01, timeout=300)
finally:
    w.call(a.disconnect, timeout=30)
    w.stop()
