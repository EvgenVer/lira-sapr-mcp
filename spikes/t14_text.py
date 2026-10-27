"""T14 probe: the loads that self weight wrote into spikes/out/t14_frame.lir."""

from pathlib import Path

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.services.textformat import TextModel

MODEL = (Path(__file__).parent / "out" / "t14_frame.lir").resolve()

adapter = ComLiraAdapter(pick_install(find_installs(), None))
adapter.connect()
try:
    print("open:", [(d.title, d.path) for d in adapter.list_documents()], flush=True)
    info, _ = adapter.open_document(str(MODEL))
    print("opened", info.path, flush=True)
    text = adapter.export_text(info.path)
    start = text.find("( 6/")
    print(text[start : start + 600])
    loads = TextModel.parse(text).loads()
    print([(ld.case, ld.target, ld.type, ld.direction, ld.values) for ld in loads])
    adapter.close_document(info.path, True)
finally:
    adapter.disconnect()
