"""Probe: which combination norms LIRA's own example models use, read from load case kinds.

SNiP 2.01.07-85* names kinds 'Мгновенное(М)', SP 20.13330 names them with Latin codes
such as 'Особое ( Ps)'. Prints the kinds of every example model (on copies).
"""

import shutil
import sys
from pathlib import Path

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.com.worker import ComWorker

sys.stdout.reconfigure(encoding="utf-8")
MANUAL = Path(r"C:\Users\Public\Documents\LIRA SAPR\LIRA SAPR 2024\Manual\RU")
OUT = Path("spikes/out/t25n").resolve()
OUT.mkdir(parents=True, exist_ok=True)

w = ComWorker()
a = ComLiraAdapter(pick_install(find_installs(), None))


def run(fn, *args):
    return w.call(fn, *args, timeout=300)


run(a.connect)
for i, src in enumerate(sorted(MANUAL.rglob("*.lir"))):
    copy = OUT / f"lmcp_n{i:02d}.lir"
    shutil.copy(src, copy)
    try:
        run(a.open_document, str(copy))
        rows = run(a.read_table, str(copy), "LoadCases")
        kinds = sorted({row[3] for row in rows if len(row) > 3})
        print(f"{i:02d} {src.name}: {len(rows)} cases; kinds {kinds}", flush=True)
    except Exception as exc:
        print(f"{i:02d} {src.name}: ERR {exc}", flush=True)
    finally:
        try:
            run(a.close_document, str(copy), True)
        except Exception as exc:
            print("   close ERR", exc, flush=True)
