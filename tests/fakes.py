"""An in-memory stand-in for ComLiraAdapter, so services and tools run without LIRA."""

from pathlib import Path

from lira_sapr_mcp.adapters.base import DocInfo, TableError, Units
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
        self.capabilities = frozenset({"OpenDocument", "ImportFile", "StartAnalysis"})
        self.table_kinds = {"Nodes_Coordinates": 2, "Elements_TypeAndNodes": 3, "LoadCases": 25}
        self.docs: dict[str, dict] = {}
        self.active: str | None = None

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

    def close_document(self, ref):
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
        d["tables"][name] = [list(r) for r in rows]
        d["modified"] = True
        return []

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
    )
    return session, adapter
