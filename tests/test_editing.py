"""High-level edits through the fake adapter: rows they write and checks they make."""

import pytest
from mcp import Client

from fakes import fake_session
from lira_sapr_mcp.server import build_server

pytestmark = pytest.mark.anyio

RECT = "Ro:10.4167 E:3e+006 B:40 H:60 NGrndPar:-1 BAR_END Mu:0.25 EF:720000 EIy:9600 STD_END"


async def call(client, name, args):
    res = await client.call_tool(name, args)
    return res


async def frame(client, tmp_path):
    model = tmp_path / "edit.lir"
    model.write_bytes(b"lir")
    await call(client, "lira_open_model", {"path": str(model)})
    nodes = [[1, 0.0, 0.0, 0.0], [2, 0.0, 0.0, 3.0]]
    await call(client, "lira_write_table", {"table": "Nodes_Coordinates", "rows": nodes})
    stiff = [[1, 0, "#ffffff", None, RECT, None, None, None, None]]
    await call(client, "lira_write_table", {"table": "Stiffnesses", "rows": stiff})
    return model


async def table(client, name):
    res = await call(client, "lira_read_table", {"table": name})
    return res.structured_content["rows"]


async def test_add_nodes_and_elements_with_stiffness(tmp_path):
    session, _ = fake_session(tmp_path)
    async with Client(build_server(session)) as client:
        model = await frame(client, tmp_path)
        added = await call(client, "lira_add_nodes", {"coordinates": [[6, 0, 3], [6, 0, 0]]})
        bars = await call(
            client, "lira_add_elements", {"nodes": [[1, 2], [2, 3], [3, 4]], "stiffness": 1}
        )
        bad = await call(client, "lira_add_elements", {"nodes": [[1, 9]]})
        elements = await table(client, "Elements_TypeAndNodes")
        stiffness = await table(client, "Elements_Stiffnesses")
    assert added.structured_content["nodes"] == [3, 4]
    assert bars.structured_content["elements"] == [1, 2, 3]
    assert bars.structured_content["backup"].startswith(str(model.parent))
    assert elements[2] == [3, 10, "3, 4"]
    assert stiffness == [[1, 1], [2, 1], [3, 1]]
    assert bad.is_error and "No nodes 9" in bad.content[0].text


async def test_stiffness_copy_assign_and_restraints(tmp_path):
    session, _ = fake_session(tmp_path)
    async with Client(build_server(session)) as client:
        await frame(client, tmp_path)
        await call(client, "lira_add_nodes", {"coordinates": [[6, 0, 3]]})
        await call(client, "lira_add_elements", {"nodes": [[1, 2], [2, 3]], "stiffness": 1})
        copied = await call(client, "lira_copy_stiffness", {"source": 1, "changes": {"B": 80}})
        wrong = await call(client, "lira_copy_stiffness", {"source": 1, "changes": {"D": 1}})
        await call(client, "lira_set_stiffness", {"elements": "2", "stiffness": 2})
        missing = await call(client, "lira_set_stiffness", {"elements": [7], "stiffness": 1})
        no_such = await call(client, "lira_set_stiffness", {"elements": [1], "stiffness": 9})
        fixed = await call(
            client, "lira_set_restraints", {"nodes": [1], "directions": ["x", "Z", "UY"]}
        )
        bad_dir = await call(client, "lira_set_restraints", {"nodes": [1], "directions": ["W"]})
        stiffnesses = await table(client, "Stiffnesses")
        assigned = await table(client, "Elements_Stiffnesses")
        restraints = await table(client, "Nodes_Restraints")
    assert copied.structured_content["stiffness"] == 2
    params = stiffnesses[1][4]
    assert "B:80 " in params and "H:60" in params
    assert "EF:-1" in params and "EIy:-1" in params  # LIRA derives them again
    assert wrong.is_error and "no parameter 'D'" in wrong.content[0].text
    assert assigned == [[1, 1], [2, 2]]
    assert missing.is_error and "No elements 7" in missing.content[0].text
    assert no_such.is_error and "No stiffness 9" in no_such.content[0].text
    assert fixed.structured_content["nodes"] == 1
    assert restraints == [[1, 1, None, 1, None, 1, None, None]]
    assert bad_dir.is_error and "Unknown directions" in bad_dir.content[0].text


async def test_self_weight_goes_to_the_adapter(tmp_path):
    session, adapter = fake_session(tmp_path)
    async with Client(build_server(session)) as client:
        model = await frame(client, tmp_path)
        await call(
            client, "lira_self_weight", {"load_case": 2, "safety_factor": 1.1, "elements": "1-2"}
        )
        added = adapter.docs[str(model)]["self_weight"]
        await call(client, "lira_self_weight", {"load_case": 1, "delete_all": True})
    assert added == (2, 1.1, [1, 2])
    assert "self_weight" not in adapter.docs[str(model)]
