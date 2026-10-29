"""Probe: which restored table makes LIRA refuse the LoadCases write after a text rebuild?

Usage: t25_order.py <model.lir>. Rebuilds a copy from its own text, then restores the
differing tables one by one in set_loads' order and prints what each write does.
"""

import shutil
import sys
from pathlib import Path

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.com.worker import ComWorker
from lira_sapr_mcp.services.loads import _import_text, _snapshot

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path("spikes/out/t25o").resolve()
OUT.mkdir(parents=True, exist_ok=True)
copy = OUT / "lmcp_t25o.lir"
shutil.copy(sys.argv[1], copy)

w = ComWorker()
a = ComLiraAdapter(pick_install(find_installs(), None))


def run(fn, *args):
    return w.call(fn, *args, timeout=600)


run(a.connect)
run(a.open_document, str(copy))
before = run(_snapshot, a, str(copy))
text = run(a.export_text, str(copy))
new = run(_import_text, a, text, "lmcp_t25o_new")
ref = new.path or new.title
for name, rows in before.items():
    if rows is None:
        continue
    try:
        now = run(a.read_table, ref, name)
    except Exception as exc:
        now = f"ERR {exc}"
    if now == rows:
        continue
    print(f"{name}: {len(rows)} rows, rebuilt has", now if isinstance(now, str) else len(now))
    try:
        print("   write:", run(a.write_table, ref, name, rows)[:3])
    except Exception as exc:
        print("   write EXC:", exc)
    print("   equal now:", run(a.read_table, ref, name) == rows)
    if name == "LoadCases":
        print("   original:", rows)
        print("   rebuilt: ", now)
run(a.close_document, ref, True)
run(a.close_document, str(copy), True)
