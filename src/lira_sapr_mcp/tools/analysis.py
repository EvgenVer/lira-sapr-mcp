"""Tools: run, watch and stop the LIRA analysis; read its protocol."""

import asyncio
import time
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from lira_sapr_mcp.errors import LiraInputError
from lira_sapr_mcp.services.session import LiraSession
from lira_sapr_mcp.tools.common import lira_errors

READ_ONLY = ToolAnnotations(readOnlyHint=True)
POLL_S = 0.5


def register(mcp: MCPServer, session: LiraSession) -> None:
    async def wait_for_end(timeout_s: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        while True:
            status = await session.run(session.adapter.analysis_status)
            if status["status"] not in ("running",) or time.monotonic() > deadline:
                return status
            await asyncio.sleep(POLL_S)

    @mcp.tool()
    @lira_errors
    async def lira_run_analysis(
        model: str | None = None, wait: bool = True, timeout_s: float | None = None
    ) -> dict[str, Any]:
        """Analyse a saved model (default: the active one).

        LIRA analyses the .lir file on disk, so save changes first (lira_save_model).
        With wait=true the call returns when the analysis ends or timeout_s passes (the
        analysis then keeps running: poll lira_analysis_status). The result includes the
        protocol verdict and every warning line (e.g. a geometrically unstable structure
        still "finishes", with warnings). Status "needs_user" means a LIRA dialog waits.
        LIRA closes the model after the analysis: reopen it to continue editing.
        """
        ref = await session.resolve(model)
        status = await session.run(session.adapter.start_analysis, ref)
        session.analysed[ref.lower()] = ref
        if not wait:
            return status
        return await wait_for_end(timeout_s or session.settings.analysis_timeout_s)

    @mcp.tool(annotations=READ_ONLY)
    @lira_errors
    async def lira_analysis_status(wait_s: float = 0) -> dict[str, Any]:
        """State of the last analysis started by this server: running, finished, failed,
        stopped or needs_user; with the protocol summary when it has ended. wait_s > 0
        waits up to that many seconds for a running analysis to end.
        """
        if wait_s > 0:
            return await wait_for_end(wait_s)
        return await session.run(session.adapter.analysis_status)

    @mcp.tool()
    @lira_errors
    async def lira_stop_analysis() -> dict[str, Any]:
        """Ask LIRA to stop the running analysis."""
        await session.run(session.adapter.stop_analysis)
        return await wait_for_end(30)

    @mcp.tool(annotations=READ_ONLY)
    @lira_errors
    async def lira_analysis_protocol(
        model: str | None = None, tail_lines: int = 200
    ) -> dict[str, Any]:
        """The solver's protocol of the last analysis of a model (default: the active one,
        or the model analysed last), last tail_lines lines.
        """
        if model is None:
            last = (await session.run(session.adapter.analysis_status))["model"]
            model = last or await session.resolve(None)
        text = await session.run(session.adapter.protocol, model)
        if text is None:
            raise LiraInputError(f"No analysis protocol found for {model}")
        lines = text.splitlines()
        return {"model": model, "lines": len(lines), "text": "\n".join(lines[-tail_lines:])}
