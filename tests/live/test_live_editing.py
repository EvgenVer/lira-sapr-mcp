"""Acceptance example 3: change the stiffness of a group of elements, analyse again and
compare the largest displacements; the original file is backed up next to the model.

On the portal frame of example 1 every bar bends in the frame plane, so doubling the
section width B doubles EF, EI and GF: all displacements halve. Self weight then follows
the new section. A factor in Stiffnesses_Factors does not change a linear analysis.
"""

import pytest
from mcp import Client
from test_live_loads import FRAME

from lira_sapr_mcp.config import Settings
from lira_sapr_mcp.server import build_server
from lira_sapr_mcp.services.session import LiraSession

pytestmark = [pytest.mark.lira, pytest.mark.anyio]


@pytest.fixture
def mcp(tmp_path):
    session = LiraSession(Settings(log_file=tmp_path / "log.txt"))
    yield build_server(session)
    session.close()


async def ok(client, name, args=None):
    res = await client.call_tool(name, args or {})
    assert not res.is_error, (name, res.content)
    return res.structured_content


async def largest_z(client, path):
    status = await ok(client, "lira_run_analysis", {"model": path, "timeout_s": 300})
    assert status["status"] == "finished", status
    moved = await ok(client, "lira_node_displacements", {"model": path, "sort_by": "Z", "top": 1})
    return abs(moved["rows"][0]["Z"])


async def test_stiffer_group_moves_less(mcp, workdir):
    path = str(workdir / "lmcp_edit.lir")
    async with Client(mcp) as client:
        await ok(client, "lira_import_text_model", {"text": FRAME, "save_as": path})
        before = await largest_z(client, path)

        await ok(client, "lira_open_model", {"path": path})
        copied = await ok(client, "lira_copy_stiffness", {"source": 1, "changes": {"B": 80}})
        assigned = await ok(
            client, "lira_set_stiffness", {"elements": "1-3", "stiffness": copied["stiffness"]}
        )
        await ok(client, "lira_save_model", {})
        wider = await largest_z(client, path)

        await ok(client, "lira_open_model", {"path": path})
        await ok(
            client, "lira_write_table", {"table": "Stiffnesses_Factors", "rows": [[1, 2.0]],
                                         "numbers": [1]}
        )  # fmt: skip
        weight = await ok(client, "lira_self_weight", {"load_case": 2, "safety_factor": 1.1})
        loads = await ok(client, "lira_read_loads", {"load_cases": [2]})
        # Only element 3, though the user had elements 1 and 2 selected in LIRA.
        await ok(client, "lira_run_script", {"code": "doc.Select('1 2', 0)"})
        await ok(client, "lira_self_weight", {"load_case": 3, "elements": [3]})
        only = await ok(client, "lira_read_loads", {"load_cases": [3]})
        await ok(client, "lira_save_model", {})
        stiffer = await largest_z(client, path)
    assert copied["stiffness"] == 2
    backup = assigned["backup"]
    assert backup and backup.endswith(".lir") and "lira-mcp-backups" in backup
    assert weight["message"] is None
    # Self weight of the 80 x 60 cm bars: 0.48 m2 x 10.4167 t/m3 x 1.1 = 5.5 t/m, type 16.
    assert {ld["target"] for ld in loads["loads"]} == {1, 2, 3}
    assert all(ld["type"] == 16 for ld in loads["loads"])
    assert loads["loads"][0]["values"][0] == pytest.approx(5.5, abs=0.01)
    assert [(ld["target"], ld["type"]) for ld in only["loads"]] == [(3, 16)]
    assert wider == pytest.approx(before / 2, rel=1e-3)
    # The factor changed nothing; case 2 (self weight, 5.5 t/m) moves less than case 1.
    assert stiffer == pytest.approx(wider, rel=1e-6)
