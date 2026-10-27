"""An in-memory stand-in for ComLiraAdapter, so services and tools run without LIRA."""

from pathlib import Path

from lira_sapr_mcp.adapters.base import DocInfo, TableError, Units
from lira_sapr_mcp.adapters.dialogs import Dialog
from lira_sapr_mcp.adapters.discovery import LiraInstall
from lira_sapr_mcp.com.worker import ComWorker
from lira_sapr_mcp.config import Settings
from lira_sapr_mcp.errors import LiraInputError
from lira_sapr_mcp.services.session import LiraSession

INSTALL = LiraInstall(2024, "LiraSapr.Application.2024", r"C:\LIRA\LiraSapr.exe", "24.2.3.1")


class FakeAdapter:
    def __init__(self, install: LiraInstall = INSTALL) -> None:
        self.install = install
        self.connected = False
        self.capabilities = frozenset({"OpenDocument", "CreateNewDocument", "ImportFile",
                                       "StartAnalysis", "StopAnalysis", "DeleteResults",
                                       "StartCmd", "SetDeadWeightLoad", "Select"})  # fmt: skip
        self.table_kinds = {"Nodes_Coordinates": 2, "Elements_TypeAndNodes": 3, "LoadCases": 25,
                            "Nodes_Restraints": 4, "Stiffnesses": 9, "Elements_Stiffnesses": 10,
                            "Stiffnesses_Factors": 28}  # fmt: skip
        self.docs: dict[str, dict] = {}
        self.active: str | None = None
        self.analysis = "idle"
        self.analysed: str | None = None
        self.deleted: set[str] = set()
        self.dialogs_shown: list[Dialog] = []  # what LIRA's windows would show

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def _get(self, ref: str | None) -> dict:
        key = ref or self.active
        for k, d in self.docs.items():
            if key in (k, d["title"]):
                return d
        raise LiraInputError(f"No open LIRA document matches {ref!r}")

    def _info(self, d: dict) -> DocInfo:
        return DocInfo(
            d["title"],
            d["path"],
            d["type"],
            d["modified"],
            d["path"] == self.active,
            d["path"].endswith(".lir"),
        )

    def list_documents(self):
        return [self._info(d) for d in self.docs.values()]

    def document_info(self, ref=None):
        if not self.docs:
            raise LiraInputError("No model is open in LIRA: open or create one first")
        return self._info(self._get(ref))

    def open_document(self, path):
        if not Path(path).is_file():
            raise LiraInputError(f"File not found: {path}")
        d = {"title": Path(path).stem, "path": path, "type": 5, "modified": False, "tables": {}}
        self.docs[path] = d
        self.active = path
        return self._info(d), ""

    def create_document(self, title, model_type, description=""):
        path = rf"C:\LIRA\Data\{title}"
        d = {"title": title, "path": path, "type": model_type, "modified": True, "tables": {}}
        self.docs[path] = d
        self.active = path
        return self._info(d)

    def save_document(self, ref, path=None):
        d = self._get(ref)
        if path:
            self.docs.pop(d["path"])
            d["path"] = path
            self.docs[path] = d
            self.active = path
            Path(path).write_bytes(b"lir")
        d["modified"] = False
        return self._info(d)

    def close_document(self, ref, discard=False):
        d = self._get(ref)
        self.docs.pop(d["path"])
        if self.active == d["path"]:
            self.active = next(iter(self.docs), None)

    def read_table(self, ref, name, numbers=None):
        return [list(r) for r in self._get(ref)["tables"].get(name, [])]

    def write_table(self, ref, name, rows, numbers=None):
        if name not in self.table_kinds:
            return [TableError(-1, -1, "unknown table")]
        d = self._get(ref)
        if numbers:  # as LIRA: replace (or add) only the rows of these numbers
            kept = [r for r in d["tables"].get(name, []) if r[0] not in numbers]
            d["tables"][name] = sorted(kept + [list(r) for r in rows], key=lambda r: r[0])
        else:
            d["tables"][name] = [list(r) for r in rows]
        d["modified"] = True
        return []

    def self_weight(self, ref, load_case, factor, elements=None):
        d = self._get(ref)
        d["self_weight"] = (load_case, factor, elements)
        d["modified"] = True
        return ""

    def run_script(self, code, ref, timeout_s):
        from lira_sapr_mcp.services.scripts import run_script

        doc = self._get(ref) if ref else None
        names = {"lira": None, "doc": doc, "adapter": self, "constants": None}
        return run_script(code, names, timeout_s)

    def _press_dialog_button(self, exe, button, title=None):  # stands for Win32, not COM
        dialog = next(d for d in self.dialogs_shown if not title or title in d.title)
        if button not in dialog.buttons:
            raise LiraInputError(f"Dialog {dialog.title!r} has no button {button!r}")
        self.dialogs_shown.remove(dialog)
        return dialog

    def model_picture(self, ref, view="isometric"):
        from lira_sapr_mcp.adapters.picture import encode_png

        self._get(ref)
        return encode_png(2, 1, bytes([0, 0, 255, 255] + [255] * 4))  # red, white

    def delete_self_weight(self, ref):
        self._get(ref).pop("self_weight", None)
        return ""

    def analysis_status(self):
        return {"status": self.analysis, "model": self.analysed}

    def start_analysis(self, ref):
        d = self._get(ref)
        if d["modified"]:
            raise LiraInputError(f"{d['title']} has unsaved changes; save first")
        self.analysis, self.analysed = "finished", d["path"]
        return {"status": "running", "model": d["path"]}

    def stop_analysis(self):
        self.analysis = "stopped"

    # Models whose names start with "frame" have results of 2 nodes and 3 elements.
    def results_info(self, model_path):
        if not Path(model_path).stem.startswith("frame") or model_path in self.deleted:
            return {"present": False}
        return {"present": True, "nodes": 2, "elements": 3, "written": "2026-10-27T10:00:00"}

    def delete_results(self, model_path):
        self.deleted.add(model_path)

    def protocol(self, model_path):
        return "Расчет успешно завершен\n" if model_path == self.analysed else None

    def export_text(self, ref):
        return self._get(ref)["text"]

    def import_file(self, path, template=""):
        text = Path(path).read_text(encoding="utf-8-sig")
        info = self.create_document(Path(path).stem, 5)
        self._get(info.path)["text"] = text
        return info

    # Beam 1 with 3 sections in t*m; node 2 moving down 1.25 mm, in m.
    # Plus plate 2 with one point, stresses in tf/m2.
    def element_forces(self, model_path, elements, cases, families=None):
        if not Path(model_path).stem.startswith("frame"):
            raise LiraInputError(f"No analysis results for {Path(model_path).stem!r}")
        rows = [
            {"family": "bar", "element": 1, "case": 1, "section": s, "N": -1.0, "My": my}
            for s, my in ((1, -2.0), (2, 3.0), (3, -2.0))
        ]
        rows.append({"family": "plate", "element": 2, "case": 1, "section": 1, "Nx": 10.0})
        return [r for r in rows if not families or r["family"] in families]

    def node_displacements(self, model_path, nodes, cases):
        return [
            {"node": n, "case": 1, "X": 0.0, "Z": -0.00125 * (n - 1), "UY": 0.001}
            for n in nodes or [1, 2]
        ]

    # Two load combinations; one design combination per limit state of bar 1.
    def load_combinations(self, model_path):
        names = [{"number": n, "name": f"DCL{n}", "formula": 1, "special": False,
                  "seismic": False} for n in (1, 2)]  # fmt: skip
        return {"code": "SP", "combinations": names}

    def combination_displacements(self, model_path, nodes, combinations):
        return [{"node": 2, "combination": c, "Z": -0.001 * c} for c in combinations or [1, 2]]

    def combination_forces(self, model_path, elements, combinations, families, limit_states):
        return [
            {"family": "bar", "element": 1, "combination": c, "limit_state": "ultimate",
             "section": 1, "My": -1.0 * c}
            for c in combinations or [1, 2]
        ]  # fmt: skip

    def periods(self, model_path, cases):
        modes = [{"mode": 1, "period": 0.43, "modal_mass": 44.3},
                 {"mode": 2, "period": 0.35, "modal_mass": 0.0}]  # fmt: skip
        return [{"case": 4, "type": 35, "modes": modes}]

    def reinforcement(self, model_path, elements, design_option=1):
        return [
            {"family": "bar", "element": 1, "section": 1, "symmetric": True, "AU1": 2.28,
             "PERC": 0.47},
            {"family": "plate", "element": 2, "AS1": 6.1, "AS3": 6.56,
             "errors": {"AS2": "section is not adequate"}},
        ]  # fmt: skip

    def fragment_loads(self, model_path, nodes, cases):
        return [{"node": 1, "case": 1, "RZ": 2.0, "RUY": 1.0}]

    def punching_loads(self, model_path, nodes, cases):
        return [{"node": 1, "case": 1, "N": 3.0}]

    def design_forces(self, model_path, elements, families, limit_states):
        return [
            {"family": "bar", "element": 1, "section": 1, "limit_state": "ultimate", "dcf": 1,
             "criterion": 2, "group": "A1", "load_cases": "1-3,-4", "with": "seismic",
             "N": -2.0, "My": 1.0}
        ]  # fmt: skip

    def units(self):
        return Units("m", "cm", "kN", "m", "kN", "m2", "mm", "kN", "m", "kN", "m2", "C")


def fake_session(tmp_path) -> tuple[LiraSession, FakeAdapter]:
    adapter = FakeAdapter()
    worker = ComWorker(init=lambda: None, uninit=lambda: None, pump=lambda: None)
    session = LiraSession(
        Settings(log_file=tmp_path / "log.txt"),
        worker=worker,
        find=lambda: [INSTALL],
        make_adapter=lambda install: adapter,
        dialogs=lambda exe: list(adapter.dialogs_shown),
        press=adapter._press_dialog_button,
    )
    return session, adapter
