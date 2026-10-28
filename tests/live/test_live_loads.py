import shutil
from pathlib import Path

import pytest

from lira_sapr_mcp.errors import LiraError
from lira_sapr_mcp.services import loads as loads_service
from lira_sapr_mcp.services.textformat import Load, TextModel

pytestmark = pytest.mark.lira

EXAMPLE = Path(r"C:\Users\Public\Documents\LIRA SAPR\LIRA SAPR 2024\Manual\RU")
EXAMPLE = EXAMPLE / "01_плоская рама ЖБ" / "01_2D рама ЖБ.lir"

# Portal frame 6 x 3 m, fixed bases, 40x60 cm bars, 10 t/m uniform load on the beam.
FRAME = """( 0/ 1; FRAME/ 2; 5/ 33; M 1 CM 100 T 1 C 1/ )
( 1/ 10 1 1 3/ 10 1 2 4/ 10 1 3 4/ )
( 3/ 1 S0 3E6 40 60/ 0 RO 2.5/ )
( 4/ 0 0 0/ 6 0 0/ 0 0 3/ 6 0 3/ )
( 5/ 1 1 2 3 4 5 6/ 2 1 2 3 4 5 6/ )
( 6/ 3 6 3 1 1/ )
( 7/ 1 10/ )
"""


@pytest.fixture
def example(workdir):
    if not EXAMPLE.exists():
        pytest.skip("LIRA example models are not installed")
    model = workdir / "lmcp_example.lir"
    shutil.copy(EXAMPLE, model)
    return model


def test_text_export_contains_loads_and_spares_user_files(lira, adapter, example):
    info, _ = lira(adapter.open_document, str(example))
    data_dir = Path(adapter.directories()["TextDataDirectory"])
    users_file = data_dir / f"{info.title}.txt"
    users_file.write_text("owner's own file", encoding="utf-8")
    try:
        text = lira(adapter.export_text, str(example))
        assert users_file.read_text(encoding="utf-8") == "owner's own file"
    finally:
        users_file.unlink()
    loads = TextModel.parse(text).loads()
    assert {ld.case for ld in loads} == {1, 2, 3, 4}


def test_new_model_from_text_keeps_loads(lira, adapter, workdir):
    target = workdir / "lmcp_frame.lir"
    info = lira(loads_service.import_text_model, adapter, FRAME, str(target))
    assert info.saved and Path(info.path) == target
    loads = lira(loads_service.read_loads, adapter, str(target))
    # LIRA pads the value row with zeros.
    assert loads == [
        {
            "case": 1,
            "target": 3,
            "type": 6,
            "direction": 3,
            "values": [10.0, 0.0, 0.0, 0.0],
            "on_node": False,
        }
    ]
    assert not lira(adapter.document_info, str(target)).modified


def as_loads(dicts):
    return [Load(**{k: v for k, v in d.items() if k != "on_node"}) for d in dicts]


def test_changing_loads_of_own_model(lira, adapter, workdir):
    """A model with LIRA's default norms survives the rebuild: loads change, rest stays."""
    model = workdir / "lmcp_frame2.lir"
    two_cases = FRAME.replace("( 6/ 3 6 3 1 1/ )", "( 6/ 3 6 3 1 1/ 4 0 1 2 2/ )").replace(
        "( 7/ 1 10/ )", "( 7/ 1 10/ 2 5/ )"
    )
    lira(loads_service.import_text_model, adapter, two_cases, str(model))
    before = {n: lira(adapter.read_table, str(model), n) for n in ("LoadCases", "Stiffnesses")}

    report = lira(loads_service.set_loads, adapter, str(model), [Load(1, 3, 6, 3, [12.5])], [1])

    assert report["loads_now"] == 2
    after = sorted(
        (ld.case, ld.target, ld.values[0])
        for ld in as_loads(lira(loads_service.read_loads, adapter, str(model)))
    )
    assert after == [(1, 3, 12.5), (2, 4, 5.0)]
    assert not lira(adapter.document_info, str(model)).modified
    for name, rows in before.items():
        assert lira(adapter.read_table, str(model), name) == rows


def test_mismatching_rebuild_is_refused_and_original_untouched(lira, adapter, example):
    """The example uses other combination norms than LIRA's default for imports, so the
    rebuilt model's load case kinds differ: the server must refuse and change nothing."""
    lira(adapter.open_document, str(example))
    original_bytes = example.read_bytes()
    original = as_loads(lira(loads_service.read_loads, adapter, str(example)))
    changed = [
        Load(ld.case, ld.target, ld.type, ld.direction, [v * 2 for v in ld.values])
        for ld in original
        if ld.case == 1
    ]

    with pytest.raises(LiraError, match="combination norms") as err:
        lira(loads_service.set_loads, adapter, str(example), changed, [1])

    assert "Мгновенное(М) -> Особое ( Ps)" in str(err.value)
    assert "original model is untouched" in str(err.value)

    assert example.read_bytes() == original_bytes
    assert as_loads(lira(loads_service.read_loads, adapter, str(example))) == original
    assert [d.path.lower() for d in lira(adapter.list_documents)].count(str(example).lower()) == 1
