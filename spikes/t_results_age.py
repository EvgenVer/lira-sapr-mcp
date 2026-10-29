"""Probe: which files LIRA writes in its work folder for an analysis, and when, compared
with the model file's time: before and after the analysis, and after the server saves a
model it only read."""

import sys
import time
from datetime import datetime
from pathlib import Path

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.com.worker import ComWorker
from lira_sapr_mcp.services import loads as loads_service

sys.stdout.reconfigure(encoding="utf-8")
FRAME = """( 0/ 1; FRAME/ 2; 5/ 33; M 1 CM 100 T 1 C 1/ )
( 1/ 10 1 1 3/ 10 1 2 4/ 10 1 3 4/ )
( 3/ 1 S0 3E6 40 60/ 0 RO 2.5/ )
( 4/ 0 0 0/ 6 0 0/ 0 0 3/ 6 0 3/ )
( 5/ 1 1 2 3 4 5 6/ 2 1 2 3 4 5 6/ )
( 6/ 3 6 3 1 1/ )
( 7/ 1 10/ )
"""
OUT = Path("spikes/out/tra").resolve()
OUT.mkdir(parents=True, exist_ok=True)
model = OUT / "lmcp_tra.lir"
model.unlink(missing_ok=True)

w = ComWorker()
a = ComLiraAdapter(pick_install(find_installs(), None))


def run(fn, *args):
    return w.call(fn, *args, timeout=300)


def t(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="milliseconds")


run(a.connect)
work = Path(run(a.directories)["WorkDirectory"])
run(loads_service.import_text_model, a, FRAME, str(model))
print("model saved:     ", t(model))
time.sleep(2)
run(a.start_analysis, str(model))
while run(a.analysis_status)["status"] == "running":
    time.sleep(0.5)
print("analysis:", run(a.analysis_status)["status"])
import hashlib
h = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
print("model after:     ", t(model), h(model))
files = sorted(work.glob("lmcp_tra*"), key=lambda p: p.stat().st_mtime)
for p in files:
    print(f"  {t(p)}  {p.stat().st_size:>8}  {p.name}")
print("results_info:", run(a.results_info, str(model)))
time.sleep(2)
run(a.open_document, str(model))
run(a.read_table, str(model), "Nodes_Coordinates")
run(a.close_document, str(model))
print("after read+close:", t(model), h(model))
