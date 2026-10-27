"""Reading analysis results through LiraResAPI.dll (runs on the COM thread).

The library reads LIRA's result files by model name (no path), in fixed units: meters,
radians, ton-force (tf) and their products. Indices: load cases and design sections from
1, history 0 outside non-linear histories. A static load case has one deformed shape (1);
a dynamic one has several, which displacements address by mode number (e.g. 1, 5, 11)
and forces by position (1, 2, 3) - checked on a live LIRA 2024 R2.
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

# LiraElementFamilyEnum -> (family name, getter prefix)
FAMILIES = {
    1: ("bar", "GetBar"),
    2: ("plate", "GetPlate"),
    3: ("solid", "GetSolid"),
    4: ("special", "GetSpecElement"),
    5: ("special_58_59", "GetSpec_58_59_"),
    6: ("special_310", "GetSpec_310_"),
    7: ("special_264", "GetSpec_264_"),
}
F, M, BI = "force", "moment", "bimoment"
FPL, MPL, S = "force_per_length", "moment_per_length", "stress"
# LiraForceEnum -> (family, component, unit kind); units as the type library states them
# (it gives Mx, My, Mz of special elements in tf, not tf*m).
FORCES = {
    1: (1, "N", F), 2: (1, "Mx", M), 3: (1, "My", M), 4: (1, "Qz", F), 5: (1, "Mz", M),
    6: (1, "Qy", F), 7: (1, "Ry", F), 8: (1, "Rz", F), 9: (1, "Bw", BI), 10: (1, "Tw", M),
    11: (2, "Nx", S), 12: (2, "Ny", S), 13: (2, "Nz", S), 14: (2, "Txy", S),
    15: (2, "Txz", S), 16: (2, "Mx", MPL), 17: (2, "My", MPL), 18: (2, "Mxy", MPL),
    19: (2, "Qx", FPL), 20: (2, "Qy", FPL), 21: (2, "Rz", S),
    22: (3, "Nx", S), 23: (3, "Ny", S), 24: (3, "Nz", S), 25: (3, "Txy", S),
    26: (3, "Txz", S), 27: (3, "Tyz", S),
    28: (4, "N", F), 29: (4, "Nx", F), 30: (4, "Ny", F), 31: (4, "Nz", F), 32: (4, "Mx", F),
    33: (4, "My", F), 34: (4, "Mz", F), 35: (4, "Qy", F), 36: (4, "Qz", F), 37: (4, "Rx", F),
    38: (4, "Ry", F), 39: (4, "Rz", F), 40: (4, "Rux", M), 41: (4, "Ruy", M),
    42: (4, "Ruz", M),
    43: (5, "Qz", F), 44: (5, "Ny", F), 45: (5, "Qx", F),
    46: (6, "N", F), 47: (6, "My", M), 48: (6, "Mx", M), 49: (6, "Qz", F), 50: (6, "Mz", M),
    51: (6, "Qy", F),
    52: (7, "N", F), 53: (7, "Qz", F), 54: (7, "Qy", F),
}  # fmt: skip


def force_kinds(family: str) -> dict[str, str]:
    """Unit kind of each component of a family, e.g. {"N": "force", "My": "moment"}."""
    code = next(c for c, (name, _) in FAMILIES.items() if name == family)
    return {comp: kind for fam, comp, kind in FORCES.values() if fam == code}


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
        shapes = _shapes(resp.LoadCases, cases)
        rows = []
        for node in _numbers(resp.NodeNumbers.AddToString()):
            for case, modes in shapes:
                for _, mode in modes:
                    row: dict[str, Any] = {"node": node, "case": case}
                    if len(modes) > 1:
                        row["shape"] = mode
                    for d in directions:
                        if d in getters:
                            row[DISPLACEMENTS[d]] = float(getters[d](node, case, mode, 0))
                    rows.append(row)
        return rows

    def element_forces(
        self,
        model_path: str,
        elements: list[int] | None,
        cases: list[int] | None,
        families: list[str] | None = None,
    ) -> list[dict]:
        """Forces and stresses per element, load case, shape and design section; each row
        names its element family, since components differ between families."""
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
        shapes = _shapes(resp.LoadCases, cases)
        getters: dict[int, Any] = {}
        rows = []
        for el in elements:
            family = FAMILIES.get(int(resp.GetFamily(el)))
            if family is None or (families and family[0] not in families):
                continue
            components = []
            for code in _numbers(resp.GetForces(el).AddToString()):
                if code in FORCES:
                    if code not in getters:
                        getters[code] = getattr(resp, family[1] + FORCES[code][1])
                    components.append((FORCES[code][1], getters[code]))
            sections = resp.GetSectionCount(el)
            for case, modes in shapes:
                for position, mode in modes:
                    for section in range(1, sections + 1):
                        row: dict[str, Any] = {"family": family[0], "element": el, "case": case}
                        if len(modes) > 1:
                            row["shape"] = mode
                        row["section"] = section
                        for name, get in components:
                            row[name] = float(get(el, section, case, position, 0))
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


def _shapes(infos: Any, wanted: list[int] | None) -> list[tuple[int, list[tuple[int, int]]]]:
    """Per load case: its deformed shapes as (position from 1, mode number)."""
    out = []
    by_number = {int(infos.Item(i).Number): infos.Item(i) for i in range(infos.Count)}
    for case in _cases(infos, wanted):
        modes = _numbers(by_number[case].DeformedShapes.AddToString()) or [1]
        out.append((case, list(enumerate(modes, start=1))))
    return out


def _cases(infos: Any, wanted: list[int] | None) -> list[int]:
    available = [int(infos.Item(i).Number) for i in range(infos.Count)]
    if wanted is None:
        return available
    missing = sorted(set(wanted) - set(available))
    if missing:
        raise LiraInputError(f"No results for load cases {missing}; available: {available}")
    return [c for c in available if c in wanted]
