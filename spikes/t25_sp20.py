"""Probe: does set_loads keep load case kinds of a model made under LIRA's default norms?

Usage: t25_sp20.py <model.lir>. Works on a copy: scales the loads of the first load case
by 1.5 through the server's set_loads and compares LoadCases before and after.
"""

import shutil
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.com.worker import ComWorker
from lira_sapr_mcp.services import loads as loads_service
from lira_sapr_mcp.services.textformat import TextModel

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path("spikes/out/t25s").resolve()
OUT.mkdir(parents=True, exist_ok=True)
copy = OUT / "lmcp_t25s.lir"
shutil.copy(sys.argv[1], copy)

def answer_no():
    """Construction-stage models make LIRA ask, on export, whether to switch the
    nonlinear analysis kind; answer 'Нет' so the copy stays as it was."""
    import win32con
    import win32gui

    from lira_sapr_mcp.adapters.dialogs import find_dialogs

    while True:
        for d in find_dialogs("LiraSapr.exe"):
            buttons = []
            win32gui.EnumChildWindows(
                d.hwnd,
                lambda h, _: buttons.append(h)
                if win32gui.GetWindowText(h).replace("&", "") == "Нет"
                else None,
                None,
            )
            for h in buttons:
                print("answered 'Нет':", d.title, d.text[0][:60], flush=True)
                win32gui.PostMessage(h, win32con.BM_CLICK, 0, 0)
        time.sleep(1)


threading.Thread(target=answer_no, daemon=True).start()
w = ComWorker()
a = ComLiraAdapter(pick_install(find_installs(), None))


def run(fn, *args):
    return w.call(fn, *args, timeout=600)


run(a.connect)
run(a.open_document, str(copy))
before = run(a.read_table, str(copy), "LoadCases")
print("kinds before:", [(r[0], r[3]) for r in before if len(r) > 3])
loads = TextModel.parse(run(a.export_text, str(copy))).loads()
case = min(ld.case for ld in loads)
changed = [replace(ld, values=[v * 1.5 for v in ld.values]) for ld in loads if ld.case == case]
print(f"case {case}: {len(changed)} loads, first before {loads[0]}")
try:
    print("set_loads:", run(loads_service.set_loads, a, str(copy), changed, [case]))
except Exception as exc:
    print("set_loads ERR:", exc)
run(a.open_document, str(copy))
after = run(a.read_table, str(copy), "LoadCases")
print("kinds after: ", [(r[0], r[3]) for r in after if len(r) > 3])
print("LoadCases equal:", after == before)
got = [ld for ld in TextModel.parse(run(a.export_text, str(copy))).loads() if ld.case == case]
print("first load after:", got[0] if got else None)
run(a.close_document, str(copy), True)
