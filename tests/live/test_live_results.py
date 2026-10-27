"""Acceptance example 1: a portal frame from text, analysed, forces match hand calculation.

Frame 6 x 3 m, fixed bases, equal 40x60 cm bars, 10 t/m on the beam. Slope-deflection
method: beam end moments -23.858 t*m, midspan +21.142 t*m, column base 11.575 t*m,
column axial force -30 t.
"""

import shutil
import time
from pathlib import Path

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
            "lira_element_forces", {"model": path, "elements": "3", "components": ["My"]}
        )
        columns = await client.call_tool(
            "lira_element_forces",
            {"elements": [1, 2], "components": ["N", "My"], "sort_by": "My", "top": None},
        )
        moved = await client.call_tool(
            "lira_node_displacements", {"model": path, "components": ["X", "Z"]}
        )
    for r in (beam, columns, moved):
        assert not r.is_error, r.content
    b = beam.structured_content["families"]["bar"]
    unit = b["units"]["My"]
    my = {r["section"]: in_tons(r["My"], unit) for r in b["rows"]}
    assert my[1] == pytest.approx(-23.858, abs=0.01)
    assert my[2] == pytest.approx(21.142, abs=0.01)
    assert my[3] == pytest.approx(-23.858, abs=0.01)
    c = columns.structured_content["families"]["bar"]
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
        res = await client.call_tool("lira_element_forces", {"model": path})
    assert res.is_error and "No analysis results" in res.content[0].text
    assert "run lira_run_analysis" in res.content[0].text


EXAMPLE_01 = (
    Path(r"C:\Users\Public\Documents\LIRA SAPR\LIRA SAPR 2024\Manual\RU")
    / "01_плоская рама ЖБ"
    / "01_2D рама ЖБ.lir"
)


async def test_design_forces_and_missing_combinations_of_example_01(mcp, workdir):
    """Frame 01 has design combinations (DCF) but no load combinations (DCL)."""
    if not EXAMPLE_01.exists():
        pytest.skip("LIRA example models are not installed")
    path = str(workdir / "lmcp_ex01.lir")
    shutil.copy(EXAMPLE_01, path)
    async with Client(mcp) as client:
        await client.call_tool("lira_open_model", {"path": path})
        status = await analyse_open(client, path)
        assert status["status"] == "finished", status
        design = await client.call_tool(
            "lira_design_forces", {"model": path, "elements": [1], "limit_states": [1]}
        )
        dcl = await client.call_tool("lira_combination_forces", {"model": path})
        rebar = await client.call_tool("lira_reinforcement", {"model": path, "elements": "1-3"})
        fragment = await client.call_tool("lira_fragment_loads", {"model": path})
        punching = await client.call_tool("lira_punching_loads", {"model": path})
    assert not rebar.is_error, rebar.content
    bars = rebar.structured_content["families"]["bar"]
    # Only the symmetric variant is selected in this example: AU1 = 2.28 cm2 at element 1.
    assert all(r["symmetric"] for r in bars["rows"])
    first = next(r for r in bars["rows"] if r["element"] == 1 and r["section"] == 1)
    assert first["AU1"] == pytest.approx(2.28, abs=0.01)
    assert fragment.is_error and "define a fragment" in fragment.content[0].text
    assert punching.is_error and "punching shear contours" in punching.content[0].text
    assert not design.is_error, design.content
    bar = design.structured_content["families"]["bar"]
    assert bar["total_rows"] >= 5
    first = bar["rows"][0]
    assert first["limit_state"] == "ultimate" and first["group"] in ("A1", "B1", "C1", "D1")
    assert first["load_cases"]
    assert dcl.is_error and "load combinations (input table DCL)" in dcl.content[0].text


EXAMPLE_04 = (
    Path(r"C:\Users\Public\Documents\LIRA SAPR\LIRA SAPR 2024\Manual\RU")
    / "04_пространственный каркас с фунд_плитой на упругом основании"
    / "04_3D каркас_упругое основание.lir"
)


async def test_plates_and_dynamic_shapes_of_example_04(mcp, workdir):
    """Frame with a slab on elastic base; load case 4 is seismic with modes 1, 5, 11."""
    if not EXAMPLE_04.exists():
        pytest.skip("LIRA example models are not installed")
    path = str(workdir / "lmcp_ex04.lir")
    shutil.copy(EXAMPLE_04, path)
    async with Client(mcp) as client:
        await client.call_tool("lira_open_model", {"path": path})
        status = await analyse_open(client, path)
        assert status["status"] == "finished", status
        forces = await client.call_tool(
            "lira_element_forces",
            {"model": path, "load_cases": [4], "sort_by": "Mx", "top": 5},
        )
        moved = await client.call_tool(
            "lira_node_displacements", {"model": path, "nodes": "100", "load_cases": [4]}
        )
        listed = await client.call_tool("lira_load_combinations", {"model": path})
        dcl_forces = await client.call_tool(
            "lira_combination_forces",
            {"model": path, "elements": "1", "combinations": [1], "limit_states": [1]},
        )
        dcl_moved = await client.call_tool(
            "lira_combination_displacements", {"model": path, "nodes": "2"}
        )
        periods = await client.call_tool("lira_periods", {"model": path})
        rebar = await client.call_tool("lira_reinforcement", {"model": path, "elements": "109"})
        plates = {"model": path, "families": ["plate"], "sort_by": "Mx", "top": 10}
        started = time.monotonic()
        every = await client.call_tool("lira_element_forces", plates)
        read_s = time.monotonic() - started
        export = workdir / "lmcp_ex04_plates.xlsx"
        env = await client.call_tool(
            "lira_element_forces",
            plates | {"envelope": True, "threshold": 1.0, "export_path": str(export)},
        )
    assert not env.is_error, env.content
    every_plate = every.structured_content["families"]["plate"]
    env_plate = env.structured_content["families"]["plate"]
    # The envelope keeps one row per plate, with the extremes over all cases and shapes.
    assert (
        env_plate["extremes"]["Mx"]["max"]["value"] == every_plate["extremes"]["Mx"]["max"]["value"]
    )
    top = env_plate["rows"][0]
    assert "case" not in top and top["Mx_max_at"]["case"] in (1, 2, 3, 4)
    assert abs(top["Mx"]) >= 1.0 and env_plate["total_rows"] < every_plate["total_rows"]
    assert env.structured_content["export"]["rows"] == env_plate["total_rows"]
    assert export.stat().st_size > 0
    print(f"example 04: {every_plate['total_rows']} plate rows read in {read_s:.1f} s")
    assert not forces.is_error, forces.content
    (seismic,) = periods.structured_content["load_cases"]
    assert seismic["case"] == 4 and len(seismic["modes"]) == 13
    assert seismic["modes"][0]["period"] == pytest.approx(0.4294, abs=1e-3)
    assert seismic["modes"][0]["modal_mass"] == pytest.approx(44.29, abs=0.01)
    plate = rebar.structured_content["families"]["plate"]
    assert plate["rows"][0]["AS1"] == pytest.approx(4.087, abs=0.01)
    combos = listed.structured_content
    assert combos["code"] == "SP" and len(combos["combinations"]) == 3
    assert [c["seismic"] for c in combos["combinations"]] == [False, True, True]
    bar = dcl_forces.structured_content["families"]["bar"]
    assert bar["total_rows"] == 2  # two design sections
    assert dcl_moved.structured_content["total_rows"] == 3
    families = forces.structured_content["families"]
    assert set(families) >= {"bar", "plate"}
    plate = families["plate"]
    assert {"Mx", "My", "Qx"} <= set(plate["units"])
    assert {r["shape"] for r in plate["rows"]} <= {1, 5, 11}
    assert plate["extremes"]["Mx"]["max"]["at"]["case"] == 4
    d = moved.structured_content
    assert sorted(r["shape"] for r in d["rows"]) == [1, 5, 11]
