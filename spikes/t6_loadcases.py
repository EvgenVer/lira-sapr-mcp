"""T6 probe: why LoadCases/DCL rows do not restore after a text import."""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, "src")
from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter  # noqa: E402
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install  # noqa: E402
from lira_sapr_mcp.services.loads import _import_text  # noqa: E402

import pythoncom  # noqa: E402

pythoncom.CoInitialize()
out = open("spikes/out/t6_loadcases.log", "w", encoding="utf-8")
a = ComLiraAdapter(pick_install(find_installs(), None))
a.connect()
src = Path("spikes/out/t6.lir").resolve()
shutil.copy(r"C:\Users\Public\Documents\LIRA SAPR\LIRA SAPR 2024\Manual\RU\01_плоская рама ЖБ\01_2D рама ЖБ.lir", src)
a.open_document(str(src))
text = a.export_text(str(src))
(Path("spikes/out/t6_export.txt")).write_text(text, encoding="utf-8")
orig = {n: a.read_table(str(src), n) for n in ("LoadCases", "DCL")}
new = _import_text(a, text, "t6")
ref = new.path
for n, rows in orig.items():
    print("==", n, "orig", rows, file=out)
    print("   new ", a.read_table(ref, n), file=out)
    errs = a.write_table(ref, n, rows)
    print("   write errors", errs, file=out)
    print("   after", a.read_table(ref, n), file=out)
a.close_document(ref)
a.close_document(str(src))
