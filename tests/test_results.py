import pytest
from mcp import Client

from fakes import fake_session
from lira_sapr_mcp.errors import LiraInputError
from lira_sapr_mcp.server import build_server
from lira_sapr_mcp.services import results as rs


def rows():
    return [
        {"element": 1, "case": 1, "section": 1, "N": -3.0, "My": -2.0},
        {"element": 1, "case": 1, "section": 2, "N": -3.0, "My": 1.5},
        {"element": 2, "case": 2, "section": 1, "N": 4.0, "My": 0.5},
    ]


def test_tons_become_kilonewtons_and_meters_millimeters():
    data = [{"element": 1, "N": 1.0, "My": 1.0}, {"node": 1, "Z": -0.002, "UY": 0.01}]
    used = rs.convert(data[:1], rs.BAR_KIND, {"force": "kN", "moment_length": "m"})
    rs.convert(data[1:], rs.DISPLACEMENT_KIND, {"length": "mm"})
    assert data[0]["N"] == pytest.approx(9.80665)
    assert data[0]["My"] == pytest.approx(9.80665)
    assert used["My"] == "kN*m" and used["N"] == "kN"
    assert data[1]["Z"] == pytest.approx(-2.0)
    assert data[1]["UY"] == 0.01


def test_unknown_units_keep_lira_units():
    data = [{"element": 1, "N": 2.0}]
    used = rs.convert(data, rs.BAR_KIND, {"force": "none"})
    assert data[0]["N"] == 2.0 and used["N"] == "t"


def test_extremes_name_their_place():
    out = rs.summarize(rows(), ["N", "My"])
    assert out["extremes"]["My"]["min"] == {
        "value": -2.0,
        "at": {"element": 1, "case": 1, "section": 1},
    }
    assert out["extremes"]["N"]["max"]["at"]["element"] == 2
    assert out["total_rows"] == 3


def test_sort_by_absolute_value_and_top():
    out = rs.summarize(rows(), ["My"], sort_by="My", top=2)
    assert [r["My"] for r in out["rows"]] == [-2.0, 1.5]
    assert "N" not in out["rows"][0]
    assert "1 more rows" in out["note"]
    signed = rs.summarize(rows(), ["My"], sort_by="My", by_abs=False, top=1)
    assert signed["rows"][0]["My"] == 1.5


def test_unknown_components_are_reported():
    out = rs.summarize(rows(), ["My", "Mz"])
    assert out["components_not_available"] == ["Mz"]
    with pytest.raises(LiraInputError):
        rs.summarize(rows(), ["My"], sort_by="Mz")


@pytest.mark.anyio
async def test_bar_forces_tool_converts_and_reduces(tmp_path):
    session, _ = fake_session(tmp_path)
    async with Client(build_server(session)) as client:
        res = await client.call_tool(
            "lira_bar_forces",
            {"model": str(tmp_path / "frame.lir"), "components": ["My"], "sort_by": "My", "top": 1},
        )
    out = res.structured_content
    assert not res.is_error, res.content
    assert out["units"] == {"My": "kN*m"}
    assert out["rows"] == [{"element": 1, "case": 1, "section": 2, "My": 29.42}]
    assert out["extremes"]["My"]["min"]["value"] == pytest.approx(-19.6133)


@pytest.mark.anyio
async def test_same_name_models_get_a_warning(tmp_path):
    session, _ = fake_session(tmp_path)
    session.analysed[str(tmp_path / "a" / "frame.lir").lower()] = "a"
    async with Client(build_server(session)) as client:
        res = await client.call_tool(
            "lira_node_displacements", {"model": str(tmp_path / "frame.lir"), "nodes": "2"}
        )
    out = res.structured_content
    assert out["extremes"]["Z"]["min"]["value"] == pytest.approx(-1.25)
    assert out["units"]["Z"] == "mm"
    assert "same name" in out["warning"]


@pytest.mark.anyio
async def test_missing_results_say_what_to_do(tmp_path):
    session, _ = fake_session(tmp_path)
    async with Client(build_server(session)) as client:
        res = await client.call_tool("lira_bar_forces", {"model": str(tmp_path / "x.lir")})
    assert res.is_error and "No analysis results" in res.content[0].text
