"""T13 probe: MainData of LiraResAPI as a "results present" flag, and DeleteResults.

Works only on test models in tests/live/_work (lmcp_large from test_live_large.py).
"""

import sys
from pathlib import Path

import win32com.client

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install, lira_directories
from lira_sapr_mcp.adapters.results import ResultsReader, _scode

WORK = Path(__file__).parents[1] / "tests" / "live" / "_work"
LARGE = WORK / "test_ten_largest_moments_of_a_large_model" / "lmcp_large.lir"


def main_data(reader: ResultsReader, stem: str):
    access = reader._access()
    req = win32com.client.CastTo(
        access.CreateNewRequest(reader._c.kLiraRequest_MainData), "ILiraMainDataRequest"
    )
    req.DocumentName = stem
    try:
        resp = access.MainData(req)
    except Exception as exc:
        return f"error scode={_scode(exc)}: {exc}"
    return resp.GetNodeCount(), resp.GetElementCount(), resp.GetHistoryCount()


def work_files(stem: str) -> list[str]:
    work = Path(lira_directories(2024)["WorkDirectory"])
    return sorted(p.name for p in work.iterdir() if p.name.lower().startswith(stem.lower()))


reader = ResultsReader(2024)
for stem in ("lmcp_ex04", "lmcp_large", "no_such_model_xyz"):
    print(stem, main_data(reader, stem))

if "--delete" in sys.argv:
    adapter = ComLiraAdapter(pick_install(find_installs(), None))
    adapter.connect()
    print("before:", len(work_files("lmcp_large")))
    adapter._app.DeleteResults(str(LARGE))
    print("after:", work_files("lmcp_large"))
    print("lmcp_large", main_data(reader, "lmcp_large"))
    adapter.disconnect()
