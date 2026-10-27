"""Acceptance example 1: a portal frame from text, analysed, forces match hand calculation.

Frame 6 x 3 m, fixed bases, equal 40x60 cm bars, 10 t/m on the beam. Slope-deflection
method: beam end moments -23.858 t*m, midspan +21.142 t*m, column base 11.575 t*m,
column axial force -30 t.
"""

import pytest
from mcp import Client
from test_live_loads import FRAME

from lira_sapr_mcp.config import Settings
from lira_sapr_mcp.server import build_server
from lira_sapr_mcp.services import results as rs
from lira_sapr_mcp.services.session import LiraSession

pytestmark = [pytest.mark.lira, pytest.mark.anyio]


@pytest.fixture
def mcp(tmp_path):
    session = LiraSession(Settings(log_file=tmp_path / "log.txt"))
    yield build_server(session)
    session.close()


def in_tons(value, unit):
    force, _, per = unit.partition("*")
    return value / (rs.TF_TO[force] * (rs.M_TO[per] if per else 1.0))


async def test_frame_forces_match_hand_calculation(mcp, workdir):
    path = str(workdir / "lmcp_res_frame.lir")
    async with Client(mcp) as client:
        made = await client.call_tool("lira_import_text_model", {"text": FRAME, "save_as": path})
        assert not made.is_error, made.content
        sections = [[1, 3], [2, 3], [3, 3]]
        res = await client.call_tool(
            "lira_write_table", {"table": "Elements_DesignSectionsCount", "rows": sections}
        )
        assert not res.is_error, res.content
        await client.call_tool("lira_save_model", {})
        await client.call_tool("lira_close_model", {})
        await client.call_tool("lira_open_model", {"path": path})
        status = await analyse_open(client, path)
        assert status["protocol"]["clean"], status
        beam = await client.call_tool(
            "lira_bar_forces", {"model": path, "elements": "3", "components": ["My"]}
        )
        columns = await client.call_tool(
            "lira_bar_forces",
            {"elements": [1, 2], "components": ["N", "My"], "sort_by": "My", "top": None},
        )
        moved = await client.call_tool(
            "lira_node_displacements", {"model": path, "components": ["X", "Z"]}
        )
    for r in (beam, columns, moved):
        assert not r.is_error, r.content
    b = beam.structured_content
    unit = b["units"]["My"]
    my = {r["section"]: in_tons(r["My"], unit) for r in b["rows"]}
    assert my[1] == pytest.approx(-23.858, abs=0.01)
    assert my[2] == pytest.approx(21.142, abs=0.01)
    assert my[3] == pytest.approx(-23.858, abs=0.01)
    c = columns.structured_content
    assert c["total_rows"] == 6
    assert in_tons(c["rows"][0]["My"], c["units"]["My"]) == pytest.approx(23.858, abs=0.01)
    bases = [r for r in c["rows"] if r["section"] == 1]
    for base in bases:
        assert abs(in_tons(base["My"], c["units"]["My"])) == pytest.approx(11.575, abs=0.01)
        assert in_tons(base["N"], c["units"]["N"]) == pytest.approx(-30.0, abs=0.01)
    d = moved.structured_content
    assert d["total_rows"] == 4
    assert d["extremes"]["Z"]["min"]["at"]["node"] in (3, 4)
    assert d["extremes"]["Z"]["min"]["value"] < 0


async def analyse_open(client, path):
    res = await client.call_tool("lira_run_analysis", {"model": path, "timeout_s": 300})
    assert not res.is_error, res.content
    return res.structured_content


async def test_results_of_a_model_never_analysed(mcp, workdir):
    path = str(workdir / "lmcp_res_none.lir")
    async with Client(mcp) as client:
        res = await client.call_tool("lira_bar_forces", {"model": path})
    assert res.is_error and "No analysis results" in res.content[0].text
