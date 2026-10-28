"""Probe: does ImportFile's template keep the combination norms of LIRA example 01?

Compares LoadCases and DCL of the original with three imports of its own text: no
template (what set_loads does now), the original as template, and a stripped copy
(no elements, nodes, stiffnesses) as template.
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
orig = OUT / "lmcp_t25_orig.lir"
shutil.copy(MANUAL / "01_плоская рама ЖБ" / "01_2D рама ЖБ.lir", orig)
tpl = OUT / "lmcp_t25_tpl.lir"
shutil.copy(orig, tpl)

w = ComWorker()
a = ComLiraAdapter(pick_install(find_installs(), None))
TABLES = ("LoadCases", "DCL")


def run(fn, *args):
    return w.call(fn, *args, timeout=180)


def tables(ref):
    out = {}
    for name in TABLES:
        try:
            out[name] = run(a.read_table, ref, name)
        except Exception as e:
            out[name] = f"ERR {e}"
    return out


def show(label, got, base):
    print(f"== {label}")
    for name in TABLES:
        same = "SAME" if got[name] == base[name] else "DIFFERS"
        print(f"  {name}: {same}")
        if same == "DIFFERS":
            print("    ", got[name])


def import_with(text, title, template):
    folder = Path(tempfile.mkdtemp(prefix="lira-mcp-"))
    src = folder / f"{title}.txt"
    src.write_text(text, encoding="utf-8-sig")
    try:
        info = run(a.import_file, str(src), template)
    except Exception as e:
        print(f"== {title}: import failed: {e}")
        return None
    ref = info.path or info.title
    got = tables(ref)
    run(a.close_document, ref, True)
    return got


run(a.connect)
run(a.open_document, str(orig))
base = tables(str(orig))
print("original:", base)
text = run(a.export_text, str(orig))

for label, template in (("no template", ""), ("original as template", str(orig))):
    got = import_with(text, f"lmcp_t25_{len(label)}", template)
    if got:
        show(label, got, base)

run(a.open_document, str(tpl))
for name in ("Elements_TypeAndNodes", "Elements_Stiffnesses", "Stiffnesses", "Nodes_Coordinates"):
    try:
        print("strip", name, run(a.write_table, str(tpl), name, []))
    except Exception as e:
        print("strip", name, "ERR", e)
run(a.save_document, str(tpl))
print("stripped template tables:", tables(str(tpl)))
for name in ("Elements_TypeAndNodes", "Nodes_Coordinates"):
    print("  left in template", name, len(run(a.read_table, str(tpl), name)))
run(a.close_document, str(tpl), True)
got = import_with(text, "lmcp_t25_stripped", str(tpl))
if got:
    show("stripped copy as template", got, base)

run(a.close_document, str(orig), True)
w.stop()
