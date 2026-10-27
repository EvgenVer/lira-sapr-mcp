"""Close documents that live tests left open in LIRA: only models in tests/live/_work."""

from pathlib import Path

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install

WORK = (Path(__file__).parents[1] / "tests" / "live" / "_work").resolve()

adapter = ComLiraAdapter(pick_install(find_installs(), None))
adapter.connect()
for doc in adapter.list_documents():
    print(doc.title, doc.path)
    if doc.path and Path(doc.path).resolve().is_relative_to(WORK):
        adapter.close_document(doc.path, True)
        print("  closed")
adapter.disconnect()
