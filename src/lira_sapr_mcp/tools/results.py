"""Tools: analysis results of load cases, reduced on the server to what the agent asks."""

from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from lira_sapr_mcp.adapters.base import norm_path, parse_numbers
from lira_sapr_mcp.adapters.results import force_kinds
from lira_sapr_mcp.services import results as rs
from lira_sapr_mcp.services.session import LiraSession
from lira_sapr_mcp.tools.common import READ_ONLY, lira_errors


def register(mcp: MCPServer, session: LiraSession) -> None:
    async def model_path(model: str | None) -> str:
        """A .lir path as given (the model may be closed: LIRA closes it after the
        analysis), else an open model, else the model analysed last."""
        if model and model.lower().endswith(".lir"):
            return model
        if model is None:
            last = (await session.run(session.adapter.analysis_status))["model"]
            if last:
                return last
        return await session.resolve(model)

    def name_warning(path: str) -> str | None:
        stem = Path(path).stem.lower()
        others = [
            p
            for k, p in session.analysed.items()
            if Path(k).stem == stem and norm_path(k) != norm_path(path)
        ]
        if others:
            return (
                f"LIRA keeps results by model name only: {others[0]} has the same name "
                "and was analysed in this session, so these results may be its results"
            )
        return None

    async def answer(
        path: str,
        rows: list[dict],
        kinds: dict[str, str],
        units: dict,
        components: list[str] | None,
        sort_by: str | None,
        by_abs: bool,
        top: int | None,
    ) -> dict[str, Any]:
        used = rs.convert(rows, kinds, units)
        wanted = components or list(kinds)
        result = {"model": path} | rs.summarize(
            rows, wanted, sort_by=sort_by, by_abs=by_abs, top=top
        )
        result["units"] = {c: used[c] for c in wanted if c in used}
        warning = name_warning(path)
        if warning:
            result["warning"] = warning
        return result

    @mcp.tool(annotations=READ_ONLY)
    @lira_errors
    async def lira_node_displacements(
        model: str | None = None,
        nodes: list[int] | str | None = None,
        load_cases: list[int] | None = None,
        components: list[str] | None = None,
        sort_by: str | None = None,
        by_abs: bool = True,
        top: int | None = 20,
    ) -> dict[str, Any]:
        """Node displacements of load cases after lira_run_analysis.

        model: .lir path (may be closed), open model, or default the model analysed last.
        nodes: [1, 5] or "1-10 15" (default all); components: X Y Z (in the displacement
        unit set in LIRA) and UX UY UZ (rad), default all. Always returns min and max of
        each component with its node and load case; rows: sorted by sort_by (by absolute
        value unless by_abs=false), first `top` rows (null = up to 500).
        """
        path = await model_path(model)
        rows = await session.run(
            session.adapter.node_displacements, path, parse_numbers(nodes), load_cases
        )
        u = await session.run(session.adapter.units)
        units = {"length": u.displacements}
        return await answer(
            path, rows, rs.DISPLACEMENT_KIND, units, components, sort_by, by_abs, top
        )

    @mcp.tool(annotations=READ_ONLY)
    @lira_errors
    async def lira_element_forces(
        model: str | None = None,
        elements: list[int] | str | None = None,
        load_cases: list[int] | None = None,
        families: list[str] | None = None,
        components: list[str] | None = None,
        sort_by: str | None = None,
        by_abs: bool = True,
        top: int | None = 20,
    ) -> dict[str, Any]:
        """Internal forces and stresses of elements in load cases after lira_run_analysis,
        answered per element family, since each family has its own components:

        bar: N, Qy, Qz (force), Mx, My, Mz (force*length), Ry, Rz (soil), Bw, Tw;
        plate: Nx, Ny, Nz, Txy, Txz (stress), Mx, My, Mxy (force*length/length),
        Qx, Qy (force/length), Rz (soil pressure); solid: Nx, Ny, Nz, Txy, Txz, Tyz;
        special, special_58_59, special_310, special_264: their forces.
        Units are those set in LIRA and are listed per component. One row per element,
        load case, shape (dynamic load cases only: the mode number) and design section
        (bars: section 1 = start; set the count in Elements_DesignSectionsCount).
        families: e.g. ["bar"] (default all). model, elements, components, sort_by,
        by_abs, top: as in lira_node_displacements, applied within each family.
        """
        path = await model_path(model)
        rows = await session.run(
            session.adapter.element_forces,
            path,
            parse_numbers(elements),
            load_cases,
            families,
            timeout=session.settings.call_timeout_s * 5,
        )
        return await forces_answer(path, rows, components, sort_by, by_abs, top)

    @mcp.tool(annotations=READ_ONLY)
    @lira_errors
    async def lira_load_combinations(model: str | None = None) -> dict[str, Any]:
        """Load combinations (DCL, РСН) of an analysed model: number, name, formula,
        special and seismic flags, and the building code they follow."""
        path = await model_path(model)
        return {"model": path} | await session.run(session.adapter.load_combinations, path)

    @mcp.tool(annotations=READ_ONLY)
    @lira_errors
    async def lira_combination_displacements(
        model: str | None = None,
        nodes: list[int] | str | None = None,
        combinations: list[int] | None = None,
        components: list[str] | None = None,
        sort_by: str | None = None,
        by_abs: bool = True,
        top: int | None = 20,
    ) -> dict[str, Any]:
        """Node displacements in load combinations (DCL, РСН) after lira_run_analysis.

        combinations: numbers from lira_load_combinations (default all). Other arguments
        and the answer as in lira_node_displacements, with "combination" in place of
        "case".
        """
        path = await model_path(model)
        rows = await session.run(
            session.adapter.combination_displacements, path, parse_numbers(nodes), combinations
        )
        u = await session.run(session.adapter.units)
        return await answer(
            path, rows, rs.DISPLACEMENT_KIND, {"length": u.displacements}, components, sort_by,
            by_abs, top,
        )  # fmt: skip

    @mcp.tool(annotations=READ_ONLY)
    @lira_errors
    async def lira_combination_forces(
        model: str | None = None,
        elements: list[int] | str | None = None,
        combinations: list[int] | None = None,
        limit_states: list[int] | None = None,
        families: list[str] | None = None,
        components: list[str] | None = None,
        sort_by: str | None = None,
        by_abs: bool = True,
        top: int | None = 20,
    ) -> dict[str, Any]:
        """Internal forces and stresses in load combinations (DCL, РСН).

        limit_states: 1 ultimate, 2 ultimate with long-term loads, 3 serviceability,
        4 serviceability with long-term loads (default all). One row per element,
        combination, limit state and design section. Other arguments and the answer as in
        lira_element_forces.
        """
        path = await model_path(model)
        rows = await session.run(
            session.adapter.combination_forces,
            path,
            parse_numbers(elements),
            combinations,
            families,
            limit_states,
            timeout=session.settings.call_timeout_s * 5,
        )
        return await forces_answer(path, rows, components, sort_by, by_abs, top)

    @mcp.tool(annotations=READ_ONLY)
    @lira_errors
    async def lira_design_forces(
        model: str | None = None,
        elements: list[int] | str | None = None,
        limit_states: list[int] | None = None,
        families: list[str] | None = None,
        components: list[str] | None = None,
        sort_by: str | None = None,
        by_abs: bool = True,
        top: int | None = 20,
    ) -> dict[str, Any]:
        """Design combinations of forces (DCF, РСУ) after lira_run_analysis.

        One row per element, design section, limit state (as in lira_combination_forces)
        and combination "dcf", with its criterion number, internal group (A1, B1, ...),
        "load_cases" that form it (LIRA's notation: "1-3,-4" = cases 1 to 3 and case 4
        with the opposite sign) and "with": crane and/or seismic when included. Other
        arguments and the answer as in lira_element_forces.
        """
        path = await model_path(model)
        rows = await session.run(
            session.adapter.design_forces,
            path,
            parse_numbers(elements),
            families,
            limit_states,
            timeout=session.settings.call_timeout_s * 5,
        )
        return await forces_answer(path, rows, components, sort_by, by_abs, top)

    async def forces_answer(
        path: str,
        rows: list[dict],
        components: list[str] | None,
        sort_by: str | None,
        by_abs: bool,
        top: int | None,
    ) -> dict[str, Any]:
        """Convert and reduce force rows separately for each element family."""
        u = await session.run(session.adapter.units)
        units = {
            "force": u.forces,
            "moment_length": u.forces_per,
            "stress": u.stresses,
            "stress_length": u.stresses_per,
        }
        by_family: dict[str, list[dict]] = {}
        for row in rows:
            by_family.setdefault(row.pop("family"), []).append(row)
        result: dict[str, Any] = {"model": path, "families": {}}
        for family, family_rows in by_family.items():
            kinds = force_kinds(family)
            used = rs.convert(family_rows, kinds, units)
            wanted = components or list(kinds)
            if sort_by and not any(sort_by in r for r in family_rows):
                summary = rs.summarize(family_rows, wanted, top=top)
                summary["note"] = f"no {sort_by} in {family} elements: rows are not sorted"
            else:
                summary = rs.summarize(family_rows, wanted, sort_by=sort_by, by_abs=by_abs, top=top)
            summary["units"] = {c: used[c] for c in wanted if c in used}
            result["families"][family] = summary
        if not by_family:
            result["note"] = "no elements of the requested families"
        warning = name_warning(path)
        if warning:
            result["warning"] = warning
        return result
