"""Probe: table parameters (GetParameters/SetParameters) of LoadCases and DCL.

Do they carry the combination norms, and can the original's parameters be set on the
model rebuilt from text so that its load case kinds match the original again?
"""

import shutil
import tempfile
from pathlib import Path

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.com.worker import ComWorker

MANUAL = Path(r"C:\Users\Public\Documents\LIRA SAPR\LIRA SAPR 2024\Manual\RU")
OUT = Path("spikes/out/t25").resolve()
OUT.mkdir(parents=True, exist_ok=True)
orig = OUT / "lmcp_t25p_orig.lir"
shutil.copy(MANUAL / "01_плоская рама ЖБ" / "01_2D рама ЖБ.lir", orig)

w = ComWorker()
a = ComLiraAdapter(pick_install(find_installs(), None))
TABLES = ("LoadCases", "DCL")


def run(fn, *args):
    return w.call(fn, *args, timeout=180)


def params(ref, name):
    doc = a.find_document(ref)
    table = a._table(doc, name, None)
    try:
        try:
            return table.GetParameters()
        except TypeError:
            return table.GetParameters([])
    finally:
        a._drop_table(doc, table)


def set_params(ref, name, pars, rows=None):
    doc = a.find_document(ref)
    a._changed(doc)
    table = a._table(doc, name, None)
    try:
        table.SetParameters(pars)
        if rows is not None:
            table.SetContents([["" if c is None else c for c in r] for r in rows])
        return table.Apply()
    finally:
        a._drop_table(doc, table)


run(a.connect)
run(a.open_document, str(orig))
base = {n: run(a.read_table, str(orig), n) for n in TABLES}
base_pars = {n: run(params, str(orig), n) for n in TABLES}
print("original params:", base_pars)
text = run(a.export_text, str(orig))

folder = Path(tempfile.mkdtemp(prefix="lira-mcp-"))
src = folder / "lmcp_t25p_new.txt"
src.write_text(text, encoding="utf-8-sig")
new = run(a.import_file, str(src), "")
ref = new.path or new.title
print("imported params:", {n: run(params, ref, n) for n in TABLES})

for name in TABLES:
    try:
        print("set params", name, run(set_params, ref, name, base_pars[name]))
    except Exception as e:
        print("set params", name, "ERR", e)
print("after params only:", {n: run(a.read_table, ref, n) == base[n] for n in TABLES})
print("  LoadCases:", run(a.read_table, ref, "LoadCases"))
for name in TABLES:
    try:
        print("set params+rows", name, run(set_params, ref, name, base_pars[name], base[name]))
    except Exception as e:
        print("set params+rows", name, "ERR", e)
print("after params+rows:", {n: run(a.read_table, ref, n) == base[n] for n in TABLES})
print("  params now:", {n: run(params, ref, n) for n in TABLES})
print("  LoadCases:", run(a.read_table, ref, "LoadCases"))
print("  DCL:", run(a.read_table, ref, "DCL"))

run(a.close_document, ref, True)
run(a.close_document, str(orig), True)
shutil.rmtree(folder, ignore_errors=True)
w.stop()
