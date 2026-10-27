import os
import subprocess
import sys

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from lira_sapr_mcp import __version__


def test_version_is_set():
    assert __version__ == "0.1.0"


def test_cli_prints_version():
    out = subprocess.run(
        [sys.executable, "-m", "lira_sapr_mcp", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == f"lira-sapr-mcp {__version__}"


@pytest.mark.anyio
async def test_server_runs_over_stdio(tmp_path):
    """The real entry point, started the way an MCP client starts it."""
    env = dict(os.environ, LIRA_MCP_CONFIG=str(tmp_path / "config.toml"))
    (tmp_path / "config.toml").write_text(f'log_file = "{(tmp_path / "s.log").as_posix()}"\n')
    params = StdioServerParameters(command=sys.executable, args=["-m", "lira_sapr_mcp"], env=env)
    async with Client(params) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        status = await client.call_tool("lira_status", {})
    assert {"lira_status", "lira_open_model", "lira_model_summary"} <= tools
    assert not status.is_error
    assert (tmp_path / "s.log").read_text(encoding="utf-8").count("starting") == 1
