"""Builds the MCP server: one LIRA session and the tool modules registered on it."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server import MCPServer

from lira_sapr_mcp import __version__
from lira_sapr_mcp.services.session import LiraSession
from lira_sapr_mcp.tools import analysis, files, results, tables

INSTRUCTIONS = """\
Drives LIRA-SAPR (LIRA-FEM) 2024 R2+ on this computer through its COM API.
Typical flow: lira_status -> lira_open_model or lira_create_model -> lira_model_summary
-> read or change input tables -> run the analysis -> read results.
Calls are executed one at a time by LIRA. Input tables use LIRA's current units, reported
by lira_model_summary. A model argument is a .lir path or a model title; when omitted, the
model active in LIRA is used. Files are backed up before the server first overwrites them.
Results tools return extremes and the top rows only, converted to LIRA's current units.
"""


def build_server(session: LiraSession) -> MCPServer:
    @asynccontextmanager
    async def lifespan(_: MCPServer) -> AsyncIterator[None]:
        try:
            yield
        finally:
            session.close()

    mcp = MCPServer("lira-sapr", version=__version__, instructions=INSTRUCTIONS, lifespan=lifespan)
    files.register(mcp, session)
    tables.register(mcp, session)
    analysis.register(mcp, session)
    results.register(mcp, session)
    return mcp
