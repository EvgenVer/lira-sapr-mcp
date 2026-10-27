import pytest
from mcp import Client

from fakes import fake_session
from lira_sapr_mcp.adapters.results import force_kinds
from lira_sapr_mcp.errors import LiraInputError
from lira_sapr_mcp.server import build_server
from lira_sapr_mcp.services import results as rs


def rows():
    return [
        {"element": 1, "case": 1, "section": 1, "N": -3.0, "My": -2.0},
        {"element": 1, "case": 1, "section": 2, "N": -3.0, "My": 1.5},
        {"element": 2, "case": 2, "section": 1, "N": 4.0, "My": 0.5},
    ]


BAR = force_kinds("bar")
PLATE = force_kinds("plate")


def test_tons_become_kilonewtons_and_meters_millimeters():
    data = [{"element": 1, "N": 1.0, "My": 1.0}, {"node": 1, "Z": -0.002, "UY": 0.01}]
    used = rs.convert(data[:1], BAR, {"force": "kN", "moment_length": "m"})
    rs.convert(data[1:], rs.DISPLACEMENT_KIND, {"length": "mm"})
    assert data[0]["N"] == pytest.approx(9.80665)
    assert data[0]["My"] == pytest.approx(9.80665)
    assert used["My"] == "kN*m" and used["N"] == "kN"
    assert data[1]["Z"] == pytest.approx(-2.0)
    assert data[1]["UY"] == 0.01


def test_unknown_units_keep_lira_units():
    data = [{"element": 1, "N": 2.0}]
    used = rs.convert(data, BAR, {"force": "none"})
    assert data[0]["N"] == 2.0 and used["N"] == "t"


def test_plate_units_per_length_and_stresses():
    row = {"Mx": 1.0, "Qx": 1.0, "Nx": 1.0}
    units = {"force": "kN", "moment_length": "cm", "stress": "MPa"}
    used = rs.convert([row], PLATE, units)
    assert row["Mx"] == pytest.approx(9.80665) and used["Mx"] == "kN*cm/cm"
    assert row["Qx"] == pytest.approx(0.0980665) and used["Qx"] == "kN/cm"
    assert row["Nx"] == pytest.approx(0.00980665) and used["Nx"] == "MPa"
    row = {"Nx": 1.0}
    used = rs.convert([row], PLATE, {"stress": "kN", "stress_length": "cm"})
    assert row["Nx"] == pytest.approx(9.80665e-4) and used["Nx"] == "kN/cm2"


def test_every_force_code_has_a_family_and_a_known_kind():
    from lira_sapr_mcp.adapters.results import FAMILIES, FORCES

    kinds = {"force", "moment", "bimoment", "force_per_length", "moment_per_length", "stress"}
    assert sorted(FORCES) == list(range(1, 55))
    assert all(fam in FAMILIES and kind in kinds for fam, _, kind in FORCES.values())


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
async def test_element_forces_are_answered_per_family(tmp_path):
    session, _ = fake_session(tmp_path)
    async with Client(build_server(session)) as client:
        res = await client.call_tool(
            "lira_element_forces",
            {"model": str(tmp_path / "frame.lir"), "sort_by": "My", "top": 1},
        )
        only_bars = await client.call_tool(
            "lira_element_forces", {"model": str(tmp_path / "frame.lir"), "families": ["bar"]}
        )
    assert not res.is_error, res.content
    bar = res.structured_content["families"]["bar"]
    assert bar["units"]["My"] == "kN*m"
    assert bar["rows"] == [{"element": 1, "case": 1, "section": 2, "N": -9.80665, "My": 29.42}]
    assert bar["extremes"]["My"]["min"]["value"] == pytest.approx(-19.6133)
    plate = res.structured_content["families"]["plate"]
    assert plate["extremes"]["Nx"]["max"]["value"] == pytest.approx(98.0665)
    assert "not sorted" in plate["note"]
    assert list(only_bars.structured_content["families"]) == ["bar"]


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
        res = await client.call_tool("lira_element_forces", {"model": str(tmp_path / "x.lir")})
    assert res.is_error and "No analysis results" in res.content[0].text


@pytest.mark.anyio
async def test_combination_tools(tmp_path):
    session, _ = fake_session(tmp_path)
    model = str(tmp_path / "frame.lir")
    async with Client(build_server(session)) as client:
        listed = await client.call_tool("lira_load_combinations", {"model": model})
        moved = await client.call_tool(
            "lira_combination_displacements", {"model": model, "sort_by": "Z"}
        )
        forces = await client.call_tool(
            "lira_combination_forces", {"model": model, "combinations": [2]}
        )
        design = await client.call_tool("lira_design_forces", {"model": model})
    assert [c["name"] for c in listed.structured_content["combinations"]] == ["DCL1", "DCL2"]
    assert moved.structured_content["rows"][0] == {"node": 2, "combination": 2, "Z": -2.0}
    bar = forces.structured_content["families"]["bar"]
    assert bar["extremes"]["My"]["min"]["at"] == {
        "element": 1, "combination": 2, "section": 1, "limit_state": "ultimate"
    }  # fmt: skip
    (row,) = design.structured_content["families"]["bar"]["rows"]
    assert row["load_cases"] == "1-3,-4" and row["group"] == "A1" and row["with"] == "seismic"
    assert row["N"] == pytest.approx(-19.6133)


@pytest.mark.anyio
async def test_periods_reinforcement_fragment_and_punching(tmp_path):
    session, _ = fake_session(tmp_path)
    model = str(tmp_path / "frame.lir")
    async with Client(build_server(session)) as client:
        periods = await client.call_tool("lira_periods", {"model": model})
        rebar = await client.call_tool("lira_reinforcement", {"model": model})
        fragment = await client.call_tool("lira_fragment_loads", {"model": model})
        punching = await client.call_tool("lira_punching_loads", {"model": model})
    (case,) = periods.structured_content["load_cases"]
    assert case["modes"][0]["period"] == 0.43
    bar = rebar.structured_content["families"]["bar"]
    assert bar["rows"] == [
        {"element": 1, "section": 1, "symmetric": True, "AU1": 2.28, "PERC": 0.47}
    ]
    plate = rebar.structured_content["families"]["plate"]
    assert plate["errors"] == [{"element": 2, "AS2": "section is not adequate"}]
    assert "errors" not in plate["rows"][0]
    units = fragment.structured_content["units"]
    assert units["RZ"] == "kN" and units["RUY"] == "kN*m"
    assert fragment.structured_content["extremes"]["RZ"]["max"]["value"] == pytest.approx(19.6133)
    assert punching.structured_content["extremes"]["N"]["max"]["value"] == pytest.approx(29.42)


def test_reinforcement_rows_keep_values_and_name_errors():
    from lira_sapr_mcp.adapters.results import _reinforcement_row

    row = _reinforcement_row(
        "bar", 1, {"AU1": (2.0, 0), "AS1": (0.0, -1), "PERC": (0.4, -71), "AU2": (0.0, 200)}
    )
    assert row["AU1"] == 2.0 and row["PERC"] == 0.4 and "AU2" not in row
    assert row["errors"] == {"AS1": "section is not adequate", "PERC": "LIRA design warning 71"}
    assert _reinforcement_row("bar", 1, {"AU1": (0.0, 200)}) is None


def test_no_results_code_is_read_from_com_exception_info():
    from lira_sapr_mcp.adapters.results import NO_RESULTS_HRESULT, _scode

    class ComError(Exception):
        hresult = -2147352567
        excepinfo = (0, None, None, None, 0, NO_RESULTS_HRESULT)

    assert _scode(ComError()) == NO_RESULTS_HRESULT


def cases_rows():
    return [
        {"element": 1, "case": c, "section": s, "N": n, "My": my}
        for c, s, n, my in ((1, 1, -3.0, -2.0), (2, 1, 1.0, 5.0), (1, 2, -1.0, 0.5),
                            (2, 2, -4.0, -0.5))
    ]  # fmt: skip


def test_threshold_keeps_rows_that_reach_it():
    assert [r["My"] for r in rs.threshold(cases_rows(), "My", 2.0)] == [-2.0, 5.0]
    assert [r["My"] for r in rs.threshold(cases_rows(), "My", 2.0, by_abs=False)] == [5.0]


def test_envelope_per_element_and_section_over_cases():
    env = rs.envelope(cases_rows(), ["N", "My"])
    assert len(env) == 2
    first = next(r for r in env if r["section"] == 1)
    assert "case" not in first
    assert (first["My_min"], first["My_max"], first["My"]) == (-2.0, 5.0, 5.0)
    assert first["My_max_at"] == {"case": 2} and first["N_min_at"] == {"case": 1}
    second = next(r for r in env if r["section"] == 2)
    assert second["N"] == -4.0


def test_export_csv_with_units_and_family_column(tmp_path):
    import pandas as pd

    tables = {"bar": cases_rows(), "plate": [{"element": 9, "case": 1, "Nx": 2.0}]}
    out = rs.export(tables, {"N": "kN", "My": "kN*m", "Nx": "kPa"}, str(tmp_path / "f.csv"))
    assert out == {"path": str(tmp_path / "f.csv"), "rows": 5}
    df = pd.read_csv(tmp_path / "f.csv", encoding="utf-8-sig")
    assert {"My, kN*m", "Nx, kPa", "family"} <= set(df.columns)
    assert list(df["family"]) == ["bar"] * 4 + ["plate"]


def test_export_xlsx_sheet_per_table_and_nested_cells(tmp_path):
    import pandas as pd

    env = rs.envelope(cases_rows(), ["My"])
    path = tmp_path / "sub" / "env.xlsx"
    rs.export({"bar": env}, {"My": "kN*m", "My_min": "kN*m"}, str(path))
    sheets = pd.read_excel(path, sheet_name=None)
    assert list(sheets) == ["bar"]
    assert sheets["bar"]["My_max_at"][0] == "case=2"
    assert "My_min, kN*m" in sheets["bar"].columns


def test_export_needs_an_absolute_csv_or_xlsx_path(tmp_path):
    with pytest.raises(LiraInputError, match="absolute"):
        rs.export({"r": []}, {}, "out.csv")
    with pytest.raises(LiraInputError, match=r"\.csv or \.xlsx"):
        rs.export({"r": []}, {}, str(tmp_path / "out.txt"))


@pytest.mark.anyio
async def test_tools_take_threshold_envelope_and_export(tmp_path):
    session, _ = fake_session(tmp_path)
    model = str(tmp_path / "frame.lir")
    target = tmp_path / "forces.xlsx"
    async with Client(build_server(session)) as client:
        env = await client.call_tool(
            "lira_combination_displacements", {"model": model, "envelope": True}
        )
        big = await client.call_tool(
            "lira_element_forces",
            {"model": model, "sort_by": "My", "threshold": 25, "export_path": str(target)},
        )
        bad = await client.call_tool("lira_element_forces", {"model": model, "threshold": 1})
    assert not env.is_error, env.content
    (row,) = env.structured_content["rows"]
    assert row["node"] == 2 and row["Z_min_at"] == {"combination": 2}
    assert row["Z"] == row["Z_min"] and "combination" not in row
    assert not big.is_error, big.content
    bar = big.structured_content["families"]["bar"]
    assert bar["total_rows"] == 1 and bar["rows"][0]["section"] == 2
    assert big.structured_content["export"] == {"path": str(target), "rows": 2}
    assert bad.is_error and "threshold needs sort_by" in bad.content[0].text


class ResultsOnly:
    def __init__(self, info):
        self.info = info

    def results_info(self, path):
        return dict(self.info)


def test_results_summary_notes_foreign_results():
    from lira_sapr_mcp.services.models import results_summary

    fresh = {"present": True, "nodes": 2, "elements": 1}
    assert "note" not in results_summary(ResultsOnly(fresh), "m.lir", 2, 1)
    assert "same name" in results_summary(ResultsOnly(fresh), "m.lir", 5, 1)["note"]
