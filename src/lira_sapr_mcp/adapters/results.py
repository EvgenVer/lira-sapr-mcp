"""Reading analysis results through LiraResAPI.dll (runs on the COM thread).

The library reads LIRA's result files by model name (no path), in fixed units: meters,
radians, ton-force and ton-force * meter. Indices: load cases and design sections from
1, deformed shape 1 for static load cases, history 0 outside non-linear histories.
"""

from pathlib import Path
from typing import Any

from lira_sapr_mcp.adapters.base import parse_numbers
from lira_sapr_mcp.errors import LiraComError, LiraInputError

# What the library raises when the model has no results files (E_UNEXPECTED).
NO_RESULTS_HRESULT = -2147418113

# Type library and class of the results library, per LIRA release.
RES_TYPELIB = {2024: ("{BD6C09E6-B5EE-4DAB-8D61-C009BA755C46}", 1, 0)}
RES_CLASS = {2024: "{4F4546AE-AC54-48A2-9414-1B9EF6519A37}"}

DISPLACEMENTS = {1: "X", 2: "Y", 3: "Z", 4: "UX", 5: "UY", 6: "UZ"}
BAR_FORCES = {1: "N", 2: "Mx", 3: "My", 4: "Qz", 5: "Mz", 6: "Qy"}


class ResultsReader:
    """A fresh results object per request: a second request through the same object
    returns garbage numbers (LIRA 2024, checked on a live install)."""

    def __init__(self, year: int) -> None:
        self.year = year
        self._c: Any = None

    def _access(self) -> Any:
        import win32com.client
        from win32com.client import gencache

        lib = RES_TYPELIB.get(self.year, RES_TYPELIB[2024])
        cls = RES_CLASS.get(self.year, RES_CLASS[2024])
        try:
            if self._c is None:
                gencache.EnsureModule(lib[0], 0, lib[1], lib[2])
                self._c = win32com.client.constants
            obj = win32com.client.Dispatch(cls)
        except Exception as exc:
            raise LiraComError(f"LIRA results library is not available: {exc}") from exc
        return win32com.client.CastTo(obj, "ILiraResultsAccess")

    def close(self) -> None:
        self._c = None

    def _query(self, model_path: str, kind: str, iface: str, method: str, fill: Any = None):
        import win32com.client

        access = self._access()
        req = win32com.client.CastTo(access.CreateNewRequest(getattr(self._c, kind)), iface)
        req.DocumentName = Path(model_path).stem
        if fill:
            fill(req)
        try:
            return getattr(access, method)(req)
        except Exception as exc:
            if _scode(exc) == NO_RESULTS_HRESULT:
                raise LiraInputError(
                    f"No analysis results for {Path(model_path).stem!r}: run "
                    "lira_run_analysis for this model first"
                ) from exc
            raise LiraComError(
                f"Reading results of {Path(model_path).stem!r} failed: {exc}"
            ) from exc

    def node_displacements(
        self, model_path: str, nodes: list[int] | None, cases: list[int] | None
    ) -> list[dict]:
        def fill(req: Any) -> None:
            if nodes:
                req.Nodes.AddFromString(" ".join(map(str, nodes)))

        resp = self._query(
            model_path,
            "kLiraRequest_LoadCaseDisplacement",
            "ILiraLoadCaseDisplacementsRequest",
            "LoadCaseDisplacements",
            fill,
        )
        directions = _numbers(resp.Directions.AddToString())
        getters = {d: getattr(resp, f"GetNode{name}") for d, name in DISPLACEMENTS.items()}
        rows = []
        for node in _numbers(resp.NodeNumbers.AddToString()):
            for case in _cases(resp.LoadCases, cases):
                row: dict[str, Any] = {"node": node, "case": case}
                for d in directions:
                    if d in getters:
                        row[DISPLACEMENTS[d]] = float(getters[d](node, case, 1, 0))
                rows.append(row)
        return rows

    def bar_forces(
        self, model_path: str, elements: list[int] | None, cases: list[int] | None
    ) -> list[dict]:
        if not elements:
            main = self._query(
                model_path, "kLiraRequest_MainData", "ILiraMainDataRequest", "MainData"
            )
            elements = list(range(1, main.GetElementCount() + 1))
        wanted = " ".join(map(str, elements))
        resp = self._query(
            model_path,
            "kLiraRequest_LoadCaseForces",
            "ILiraLoadCaseForcesRequest",
            "LoadCaseForces",
            lambda req: req.Elements.AddFromString(wanted),
        )
        bar = self._c.kLiraFamily_Bar
        rows = []
        for el in elements:
            if resp.GetFamily(el) != bar:
                continue
            available = set(_numbers(resp.GetForces(el).AddToString()))
            getters = {
                f: getattr(resp, f"GetBar{name}")
                for f, name in BAR_FORCES.items()
                if f in available
            }
            for case in _cases(resp.LoadCases, cases):
                for section in range(1, resp.GetSectionCount(el) + 1):
                    row: dict[str, Any] = {"element": el, "case": case, "section": section}
                    for f, get in getters.items():
                        row[BAR_FORCES[f]] = float(get(el, section, case, 1, 0))
                    rows.append(row)
        return rows


def _scode(exc: Exception) -> int | None:
    """The error code of a COM exception: inside its exception info when it has one."""
    info = getattr(exc, "excepinfo", None)
    if info and len(info) > 5 and info[5]:
        return int(info[5])
    return getattr(exc, "hresult", None)


def _numbers(text: str) -> list[int]:
    return parse_numbers(str(text or "")) or []


def _cases(infos: Any, wanted: list[int] | None) -> list[int]:
    available = [int(infos.Item(i).Number) for i in range(infos.Count)]
    if wanted is None:
        return available
    missing = sorted(set(wanted) - set(available))
    if missing:
        raise LiraInputError(f"No results for load cases {missing}; available: {available}")
    return [c for c in available if c in wanted]
