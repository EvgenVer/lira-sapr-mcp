"""Probe: strip a copy of example 01 (select all, delete, pack) and import its text with
the stripped copy as ImportFile template. Do load case kinds and DCL match the original?
"""

import shutil
import tempfile
import threading
import time
from pathlib import Path

import pythoncom

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.dialogs import find_dialogs
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.com.worker import ComWorker

MANUAL = Path(r"C:\Users\Public\Documents\LIRA SAPR\LIRA SAPR 2024\Manual\RU")
OUT = Path("spikes/out/t25").resolve()
OUT.mkdir(parents=True, exist_ok=True)
orig = OUT / "lmcp_t25s_orig.lir"
shutil.copy(MANUAL / "01_плоская рама ЖБ" / "01_2D рама ЖБ.lir", orig)
tpl = OUT / "lmcp_t25s_tpl.lir"
shutil.copy(orig, tpl)

w = ComWorker()
install = pick_install(find_installs(), None)
a = ComLiraAdapter(install)
TABLES = ("LoadCases", "DCL")
COUNTS = ("Nodes_Coordinates", "Elements_TypeAndNodes", "Stiffnesses")


def run(fn, *args, timeout=180):
    return w.call(fn, *args, timeout=timeout)


def watch_dialogs(stop):
    while not stop.is_set():
        for d in find_dialogs(install.exe):
            print("   DIALOG:", d.describe())
        time.sleep(2)


def counts(ref):
    out = {}
    for n in COUNTS:
        try:
            out[n] = len(run(a.read_table, ref, n))
        except Exception as e:
            out[n] = f"ERR {e}"
    return out


def cmd(ref, number, wait=3.0):
    doc = a.find_document(ref)
    doc.Activate()
    a._changed(doc)
    a._app.StartCmd(number)
    end = time.monotonic() + wait
    while time.monotonic() < end:
        pythoncom.PumpWaitingMessages()
        time.sleep(0.1)


def select_all(ref):
    doc = a.find_document(ref)
    return doc.Select("all", 0), doc.Select("all", 1)


stop = threading.Event()
threading.Thread(target=watch_dialogs, args=(stop,), daemon=True).start()

run(a.connect)
run(a.open_document, str(orig))
base = {n: run(a.read_table, str(orig), n) for n in TABLES}
text = run(a.export_text, str(orig))
run(a.close_document, str(orig), True)

run(a.open_document, str(tpl))
print("template before:", counts(str(tpl)))
print("select all:", run(select_all, str(tpl)))
run(cmd, str(tpl), 57632)
print("after delete:", counts(str(tpl)))
run(cmd, str(tpl), 5089)
print("after pack:", counts(str(tpl)))
print("template tables same as original:",
      {n: run(a.read_table, str(tpl), n) == base[n] for n in TABLES})
run(a.save_document, str(tpl))
run(a.close_document, str(tpl), True)

folder = Path(tempfile.mkdtemp(prefix="lira-mcp-"))
src = folder / "lmcp_t25s_new.txt"
src.write_text(text, encoding="utf-8-sig")
try:
    new = run(a.import_file, str(src), str(tpl))
    ref = new.path or new.title
    got = {n: run(a.read_table, ref, n) for n in TABLES}
    print("imported with template:", counts(ref))
    for n in TABLES:
        print(f"  {n}:", "SAME" if got[n] == base[n] else f"DIFFERS {got[n]}")
    run(a.close_document, ref, True)
except Exception as e:
    print("import with template failed:", e)
shutil.rmtree(folder, ignore_errors=True)
stop.set()
w.stop()
