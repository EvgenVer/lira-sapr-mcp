"""T19 probe: does a second "fit in window" after a pause fit the frame vertically?"""

from pathlib import Path

from lira_sapr_mcp.adapters import com_adapter
from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install

MODEL = (Path(__file__).parents[1] / "tests/live/_work/test_picture_of_the_frame/lmcp_picture.lir").resolve()
OUT = Path(__file__).parent / "out"

adapter = ComLiraAdapter(pick_install(find_installs(), None))
adapter.connect()
try:
    info, _ = adapter.open_document(str(MODEL))
    adapter._settle(1.5)
    (OUT / "t19_fit1.png").write_bytes(adapter.model_picture(info.path, "xoz"))
    adapter._call("StartCmd", adapter._app.StartCmd, com_adapter.FIT_IN_WINDOW)
    adapter._settle(1.5)
    (OUT / "t19_fit2.png").write_bytes(adapter.model_picture(info.path, "current"))
    adapter.close_document(info.path, True)
finally:
    adapter.disconnect()
