"""Turn raw result rows into small answers: units, selection, extremes, top N."""

from typing import Any

from lira_sapr_mcp.errors import LiraInputError

TF_TO = {
    "t": 1.0,
    "kg": 1000.0,
    "g": 1e6,
    "N": 9806.65,
    "kN": 9.80665,
    "MN": 0.00980665,
    "lb": 2204.62262,
    "kips": 2.20462262,
}
M_TO = {"m": 1.0, "cm": 100.0, "mm": 1000.0, "ft": 3.28083990, "in": 39.3700787}

DISPLACEMENT_KIND = {
    "X": "length",
    "Y": "length",
    "Z": "length",
    "UX": "angle",
    "UY": "angle",
    "UZ": "angle",
}


# 1 tf/m2 in pressure units, for stresses set in LIRA as Pa, kPa or MPa.
TFM2_TO = {"Pa": 9806.65, "kPa": 9.80665, "MPa": 0.00980665}


def _known(value: str | None, table: dict, default: str) -> str:
    # A unit LIRA reports that we do not know (e.g. "none") falls back to LIRA's own.
    return value if value in table else default


def convert(rows: list[dict], kinds: dict[str, str], units: dict[str, str]) -> dict[str, str]:
    """Convert LIRA's result units (m, rad, tf and products) in place; return the units.

    units: "length" (displacements), "force" and "moment_length" (forces), "stress" and
    "stress_length" (stresses), as set in LIRA.
    """
    length = _known(units.get("length"), M_TO, "m")
    force = _known(units.get("force"), TF_TO, "t")
    per = _known(units.get("moment_length"), M_TO, "m")
    f, lf = TF_TO[force], M_TO[per]
    factors = {
        "length": (M_TO[length], length),
        "angle": (1.0, "rad"),
        "force": (f, force),
        "moment": (f * lf, f"{force}*{per}"),
        "bimoment": (f * lf * lf, f"{force}*{per}2"),
        "force_per_length": (f / lf, f"{force}/{per}"),
        "moment_per_length": (f, f"{force}*{per}/{per}"),
    }
    stress = units.get("stress")
    if stress in TFM2_TO:
        factors["stress"] = (TFM2_TO[stress], stress)
    else:
        sf = _known(stress, TF_TO, "t")
        sl = _known(units.get("stress_length"), M_TO, "m")
        factors["stress"] = (TF_TO[sf] / M_TO[sl] ** 2, f"{sf}/{sl}2")
    for row in rows:
        for comp, kind in kinds.items():
            if comp in row:
                row[comp] = row[comp] * factors[kind][0]
    return {comp: factors[kind][1] for comp, kind in kinds.items()}


def summarize(
    rows: list[dict],
    components: list[str],
    *,
    sort_by: str | None = None,
    by_abs: bool = True,
    top: int | None = 20,
    max_rows: int = 500,
) -> dict[str, Any]:
    """Extremes per component and the rows the agent asked for, never thousands of them."""
    present = [c for c in components if any(c in r for r in rows)]
    unknown = sorted(set(components) - set(present))
    extremes = {}
    for comp in present:
        vals = [r for r in rows if comp in r]
        lo = min(vals, key=lambda r: r[comp])
        hi = max(vals, key=lambda r: r[comp])
        extremes[comp] = {
            "min": {"value": lo[comp], "at": _where(lo)},
            "max": {"value": hi[comp], "at": _where(hi)},
        }
    selected = rows
    if sort_by:
        if sort_by not in present:
            raise LiraInputError(f"Cannot sort by {sort_by!r}; components: {present}")
        selected = sorted(
            (r for r in rows if sort_by in r),
            key=lambda r: abs(r[sort_by]) if by_abs else r[sort_by],
            reverse=True,
        )
    limit = min(top, max_rows) if top else max_rows
    shown = [
        {k: _round(v) for k, v in r.items() if k in present or k in LOCATION_KEYS}
        for r in selected[:limit]
    ]
    result: dict[str, Any] = {
        "total_rows": len(rows),
        "extremes": {
            c: {k: {"value": _round(v["value"]), "at": v["at"]} for k, v in e.items()}
            for c, e in extremes.items()
        },
        "rows": shown,
        "rows_shown": len(shown),
    }
    if unknown:
        result["components_not_available"] = unknown
    if len(selected) > len(shown):
        result["note"] = f"{len(selected) - len(shown)} more rows not shown: narrow the request"
    return result


# Where a value is: kept in every row shown and in the place of each extreme.
LOCATION_KEYS = (
    "node",
    "element",
    "case",
    "combination",
    "shape",
    "section",
    "symmetric",
    "limit_state",
    "dcf",
    "criterion",
    "group",
    "load_cases",
    "with",
)


def _where(row: dict) -> dict:
    return {k: row[k] for k in LOCATION_KEYS if k in row}


def _round(v: Any) -> Any:
    return float(f"{v:.6g}") if isinstance(v, float) else v
