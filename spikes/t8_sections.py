"""Probe: columns of the design sections table on a text-imported frame."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tests" / "live"))
from test_live_loads import FRAME  # noqa: E402

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.com.worker import ComWorker
from lira_sapr_mcp.services.loads import import_text_model

w = ComWorker()
a = ComLiraAdapter(pick_install(find_installs(), None))
path = str(Path("tests/live/_work/probe/lmcp_sec.lir").resolve())
try:
    w.call(a.connect, timeout=180)
    print([k for k in a.table_kinds if "Section" in k])
    info = w.call(import_text_model, a, FRAME, path, timeout=180)
    print(info)
    print(w.call(a.read_table, path, "Elements_DesignSectionsCount", None, timeout=60))
    print(w.call(a.write_table, path, "Elements_DesignSectionsCount", [[1, 3], [2, 3], [3, 3]], None, timeout=60))
    print(w.call(a.read_table, path, "Elements_DesignSectionsCount", None, timeout=60))
    w.call(a.close_document, path, timeout=60)
finally:
    w.call(a.disconnect, timeout=30)
    w.stop()
