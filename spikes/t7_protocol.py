"""T7 probe: analysis files and protocol for a good and a broken (unrestrained) frame."""

import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
import pythoncom  # noqa: E402
import win32com.client  # noqa: E402

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter  # noqa: E402
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install  # noqa: E402
from lira_sapr_mcp.services.loads import import_text_model  # noqa: E402

FRAME = Path("tests/live/test_live_loads.py").read_text(encoding="utf-8").split('FRAME = """')[1].split('"""')[0]
BROKEN = FRAME.replace("( 5/ 1 1 2 3 4 5 6/ 2 1 2 3 4 5 6/ )\n", "")
out = open("spikes/out/t7_protocol.log", "w", encoding="utf-8", buffering=1)
pythoncom.CoInitialize()
a = ComLiraAdapter(pick_install(find_installs(), None))
a.connect()
events = []


class Ev:
    def OnAnalysisStarting(self, Stage):
        events.append(("start", Stage))

    def OnAnalysisFinished(self, FinishCode):
        events.append(("finished", FinishCode))

    def OnAnalysisStopped(self, StopCode):
        events.append(("stopped", StopCode))


win32com.client.WithEvents(a._app, Ev)
work = Path(a.directories()["WorkDirectory"])
for name, text in (("t7good", FRAME), ("t7bad", BROKEN)):
    path = Path(f"spikes/out/{name}.lir").resolve()
    import_text_model(a, text, str(path))
    events.clear()
    t0 = time.time()
    print("docs before start:", [d.path for d in a.list_documents()], file=out)
    ok = a._app.StartAnalysis(str(path))
    print("docs right after start:", [d.path for d in a.list_documents()], file=out)
    while time.time() - t0 < 60 and not any(e[0] in ("finished", "stopped") for e in events):
        pythoncom.PumpWaitingMessages()
        time.sleep(0.05)
    print(f"== {name}: start={ok} events={events} {time.time() - t0:.1f}s", file=out)
    for f in sorted(work.glob(f"{name}*")):
        print("   file", f.name, f.stat().st_size, file=out)
    for f in (work / "PackageAnalysisLog.TXT", work / f"{name}.ald"):
        if f.exists():
            raw = f.read_bytes()
            for enc in ("utf-8-sig", "cp1251", "utf-16"):
                try:
                    txt = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    pass
            print(f"   --- {f.name} ({enc}):\n{txt[-1500:]}", file=out)
    print("docs after finish:", [d.path for d in a.list_documents()], file=out)
    for d in a.list_documents():
        a.close_document(d.path or d.title)
