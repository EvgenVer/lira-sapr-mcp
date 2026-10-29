"""Probe: after a text rebuild of an SP 20 model, does writing back the original LoadCases
rows restore the load case kinds? (SP 20 is LIRA's default norms, so the names exist in
the rebuilt model's dictionary.) Usage: t25_restore.py <model.lir>; works on a copy.
"""

import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.com.worker import ComWorker

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path("spikes/out/t25r").resolve()
OUT.mkdir(parents=True, exist_ok=True)
copy = OUT / "lmcp_t25r.lir"
shutil.copy(sys.argv[1], copy)


def answer_no():
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
                print("answered 'Нет':", d.title, flush=True)
                win32gui.PostMessage(h, win32con.BM_CLICK, 0, 0)
        time.sleep(1)


threading.Thread(target=answer_no, daemon=True).start()
w = ComWorker()
a = ComLiraAdapter(pick_install(find_installs(), None))


def run(fn, *args):
    return w.call(fn, *args, timeout=600)


def kinds(rows):
    return [(r[0], r[3]) for r in rows if len(r) > 3]


run(a.connect)
run(a.open_document, str(copy))
orig = run(a.read_table, str(copy), "LoadCases")
print("original:", kinds(orig))
text = run(a.export_text, str(copy))
for line in text.splitlines():
    if line.lstrip().startswith("( 8/") or line.lstrip().startswith("(8/"):
        print("document 8 head:", line[:200])
folder = Path(tempfile.mkdtemp(prefix="lira-mcp-"))
src = folder / "lmcp_t25r_new.txt"
src.write_text(text, encoding="utf-8-sig")
new = run(a.import_file, str(src), "")
ref = new.path or new.title
print("rebuilt: ", kinds(run(a.read_table, ref, "LoadCases")))
print("write errors:", run(a.write_table, ref, "LoadCases", orig))
back = run(a.read_table, ref, "LoadCases")
print("restored:", kinds(back))
print("restored equals original:", back == orig)
run(a.close_document, ref, True)
run(a.close_document, str(copy), True)
