"""Tools: analysis results of load cases, reduced on the server to what the agent asks."""

from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from lira_sapr_mcp.adapters.base import norm_path, parse_numbers
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
    async def lira_bar_forces(
        model: str | None = None,
        elements: list[int] | str | None = None,
        load_cases: list[int] | None = None,
        components: list[str] | None = None,
        sort_by: str | None = None,
        by_abs: bool = True,
        top: int | None = 20,
    ) -> dict[str, Any]:
        """Internal forces in bar elements of load cases after lira_run_analysis.

        One row per element, load case and design section (section 1 = start of the bar;
        the number of sections is set per element in Elements_DesignSectionsCount).
        Components: N, Qy, Qz (force unit set in LIRA), Mx, My, Mz (force * length).
        model, elements, sort_by, by_abs, top: as in lira_node_displacements. Non-bar
        elements are skipped.
        """
        path = await model_path(model)
        rows = await session.run(
            session.adapter.bar_forces, path, parse_numbers(elements), load_cases
        )
        u = await session.run(session.adapter.units)
        units = {"force": u.forces, "moment_length": u.forces_per}
        return await answer(path, rows, rs.BAR_KIND, units, components, sort_by, by_abs, top)
