"""Adapter over the LIRA COM API (LiraSapr.Application and newer LiraSapphire.Application).

Every method here must run on the COM worker thread. What a given LIRA release can do is
read from its type library at connect time (``capabilities``), so new methods and input
tables of newer releases show up without code changes.
"""

import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from lira_sapr_mcp.adapters.analysis import (
    AnalysisState,
    make_event_handler,
    protocol_path,
    read_protocol,
    summarize_protocol,
)
from lira_sapr_mcp.adapters.base import (
    UNIT_NAMES,
    DocInfo,
    TableError,
    Units,
    decode_lira_text,
    norm_path,
    normalize_rows,
    parse_table_errors,
)
from lira_sapr_mcp.adapters.discovery import LiraInstall, lira_directories
from lira_sapr_mcp.adapters.results import ResultsReader
from lira_sapr_mcp.errors import LiraComError, LiraInputError

log = logging.getLogger(__name__)

TABLE_PREFIX = "kLiraTable_"
# Name of the scratch input tables the server creates and removes again.
TEMP_TABLE_MARK = "lira-mcp-"
NOT_TABLES = {"AllTables", "Group", "Cnt"}
APP_METHODS = (
    "OpenDocument",
    "CreateNewDocument",
    "ImportFile",
    "StartAnalysis",
    "StartAnalysisOnServer",
    "StopAnalysis",
    "DeleteResults",
    "StartZip",
    "StartUnzip",
    "StartCmd",
)
# Menu command "Create text file" (menu resource of Visor.resources.dll).
EXPORT_TEXT_CMD = {2024: 5049}
DOC_METHODS = ("SetGenerateCsvTables", "SetDeadWeightLoad", "SetSoilModel", "Select")
# LiraDeadWeightLoadEnum: add to all or selected elements, delete all; LiraSelEnum elements.
DEAD_ALL, DEAD_SELECTED, DEAD_DELETE = 32, 16, -1
SEL_ELEMENTS = 0
# LiraCmdIdEnum: projections for pictures, and "fit in window".
VIEWS = {"current": 0, "isometric": 5249, "xoz": 5112, "xoy": 5113}
FIT_IN_WINDOW = 5085


def com_message(exc: BaseException) -> str:
    """Readable text of a pywin32 ``com_error``."""
    args = getattr(exc, "args", ())
    if len(args) >= 3 and isinstance(args[2], tuple) and len(args[2]) >= 3 and args[2][2]:
        return str(args[2][2]).strip()
    if len(args) >= 2 and args[1]:
        return str(args[1]).strip()
    return repr(exc)


class ComLiraAdapter:
    def __init__(self, install: LiraInstall) -> None:
        self.install = install
        self._app: Any = None
        self._c: Any = None
        self.capabilities: frozenset[str] = frozenset()
        self.table_kinds: dict[str, int] = {}
        # Documents whose "modified" flag was set only by our own reads: LIRA marks a
        # document modified when a scratch input table is created and removed in it.
        self._dirty_by_reads: set[str] = set()
        self.analysis = AnalysisState()
        self._events: Any = None
        self.results = ResultsReader(install.year)

    # --- connection -----------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._app is not None

    def connect(self) -> None:
        """Start or attach to LIRA and read what this release supports."""
        if self._app is not None:
            return
        import win32com.client
        from win32com.client import gencache

        try:
            app = gencache.EnsureDispatch(self.install.progid)
        except Exception as exc:
            raise LiraComError(
                f"Could not start LIRA {self.install.year} ({self.install.progid}): "
                f"{com_message(exc)}. Check that LIRA starts by hand and its license key "
                "is available."
            ) from exc
        self._app = app
        self._c = win32com.client.constants
        names = {k for d in self._c.__dicts__ for k in d}
        self.table_kinds = {
            k[len(TABLE_PREFIX) :]: getattr(self._c, k)
            for k in names
            if k.startswith(TABLE_PREFIX) and k[len(TABLE_PREFIX) :] not in NOT_TABLES
        }
        caps = {m for m in APP_METHODS if hasattr(app, m)}
        doc_cls = type(app).__module__
        module = __import__(doc_cls, fromlist=["ILiraDocument"])
        doc_iface = getattr(module, "ILiraDocument", None)
        caps |= {m for m in DOC_METHODS if doc_iface is not None and hasattr(doc_iface, m)}
        self.capabilities = frozenset(caps)
        self._events = win32com.client.WithEvents(app, make_event_handler(self.analysis))
        log.info("connected to %s, capabilities: %s", self.install.progid, sorted(caps))
        dirs = self.directories()
        folder = dirs.get("TextDataDirectory") or dirs.get("DataDirectory")
        if folder:
            return_parked_files(Path(folder))

    def disconnect(self) -> None:
        """Drop our references to LIRA's COM objects (on the COM thread, before it ends).

        LIRA keeps running with its documents; only this server lets go of it.
        """
        import gc

        self._events = None
        self._app = None
        self._c = None
        self.results.close()
        gc.collect()

    def _cast(self, obj: Any, iface: str) -> Any:
        import win32com.client

        return win32com.client.CastTo(obj, iface)

    def _call(self, what: str, fn: Any, *args: Any) -> Any:
        try:
            return fn(*args)
        except LiraInputError:
            raise
        except Exception as exc:
            raise LiraComError(f"{what} failed: {com_message(exc)}") from exc

    # --- documents ------------------------------------------------------------------

    @staticmethod
    def _key(doc: Any) -> str:
        return norm_path(str(doc.PathName)) or str(doc.Title).lower()

    def _modified(self, doc: Any) -> bool:
        return bool(doc.IsModified()) and self._key(doc) not in self._dirty_by_reads

    def _maybe_edited(self, doc: Any) -> bool:
        """LIRA says modified, but we counted that as our own reads: the owner may also
        have edited the model in LIRA's window since, and we cannot tell the two apart."""
        return bool(doc.IsModified()) and self._key(doc) in self._dirty_by_reads

    def _save_possible_edits(self, doc: Any) -> None:
        """Save a model whose only known changes are our reads, so that edits the owner
        may have made in LIRA meanwhile are neither lost nor left out of an analysis."""
        if self._maybe_edited(doc) and str(doc.PathName).lower().endswith(".lir"):
            log.info("saving %s before closing or analysing it", doc.PathName)
            self._changed(doc)
            self._call("Save", doc.Save, False)

    @contextmanager
    def _reading(self, doc: Any) -> Iterator[None]:
        """Wrap a read that LIRA may count as a change of ``doc``."""
        was_modified = self._modified(doc)
        try:
            yield
        finally:
            if not was_modified:
                self._dirty_by_reads.add(self._key(doc))

    def _changed(self, doc: Any) -> None:
        self._dirty_by_reads.discard(self._key(doc))

    def _info(self, doc: Any, active_path: str | None = None) -> DocInfo:
        path = str(doc.PathName or "")
        if active_path is None:
            active = self._app.ActiveDocument
            active_path = str(active.PathName) if active is not None else ""
        return DocInfo(
            title=str(doc.Title),
            path=path,
            model_type=int(doc.SystemLabel),
            modified=self._modified(doc),
            active=norm_path(path) == norm_path(active_path),
            saved=path.lower().endswith(".lir"),
        )

    def _docs(self) -> list[Any]:
        return [self._app.Document(i) for i in range(self._app.DocumentCount)]

    def list_documents(self) -> list[DocInfo]:
        self.connect()
        active = self._app.ActiveDocument
        active_path = str(active.PathName) if active is not None else ""
        return [self._info(d, active_path) for d in self._docs()]

    def find_document(self, ref: str) -> Any:
        """Find an open document by file path or by title."""
        self.connect()
        docs = self._docs()
        target = norm_path(ref)
        for d in docs:
            if norm_path(str(d.PathName)) == target:
                return d
        by_title = [d for d in docs if str(d.Title).lower() == ref.lower()]
        if len(by_title) == 1:
            return by_title[0]
        open_now = ", ".join(str(d.PathName) for d in docs) or "none"
        raise LiraInputError(f"No open LIRA document matches {ref!r}. Open documents: {open_now}")

    def document_info(self, ref: str | None = None) -> DocInfo:
        """Plain data about ``ref`` (path or title), or about the active document."""
        self.connect()
        if ref:
            return self._info(self.find_document(ref))
        active = self._app.ActiveDocument
        if active is None:
            raise LiraInputError("No model is open in LIRA: open or create one first")
        return self._info(active)

    def open_document(self, path: str) -> tuple[DocInfo, str]:
        self.connect()
        p = Path(path)
        if not p.is_file():
            raise LiraInputError(f"File not found: {path}")
        for d in self._docs():
            if norm_path(str(d.PathName)) == norm_path(str(p)):
                self._call("Activate", d.Activate)
                return self._info(d), "already open"
        res = self._call("OpenDocument", self._app.OpenDocument, str(p.resolve()), False, True)
        doc, msgs = (res if isinstance(res, tuple) else (res, ""))[:2]
        if doc is None:
            raise LiraComError(f"LIRA could not open {path}: {msgs}")
        return self._info(doc), str(msgs or "")

    def create_document(self, title: str, model_type: int, description: str = "") -> DocInfo:
        self.connect()
        bad = set(",.<>()#?*|\\/:")
        if not title or len(title) > 30 or bad & set(title):
            raise LiraInputError(
                "Title must be 1-30 characters without any of , . < > ( ) # ? * | \\ / :"
            )
        doc = self._call(
            "CreateNewDocument",
            self._app.CreateNewDocument,
            title,
            model_type,
            description,
            self._c.kLiraLoadVaksType_Design,
        )
        return self._info(doc)

    def import_file(self, path: str, template: str = "") -> DocInfo:
        self.connect()
        if not Path(path).is_file():
            raise LiraInputError(f"File not found: {path}")
        doc = self._call("ImportFile", self._app.ImportFile, str(Path(path).resolve()), template)
        return self._info(doc)

    def save_document(self, ref: str, path: str | None = None) -> DocInfo:
        doc = self.find_document(ref)
        self._call("Activate", doc.Activate)
        if path:
            target = Path(path)
            if target.suffix.lower() != ".lir":
                raise LiraInputError("LIRA models are saved with the .lir extension")
            target.parent.mkdir(parents=True, exist_ok=True)
            self._changed(doc)
            self._call("SaveAs", doc.SaveAs, str(target.resolve()), False)
        else:
            if not str(doc.PathName).lower().endswith(".lir"):
                raise LiraInputError("This model has never been saved: give a .lir path")
            self._changed(doc)
            self._call("Save", doc.Save, False)
        return self._info(doc)

    def close_document(self, ref: str, discard: bool = False) -> None:
        """Close a document. LIRA's Close drops unsaved changes, so unless ``discard``
        a saved model that may hold the owner's edits is saved first; callers refuse to
        close models with changes of their own."""
        doc = self.find_document(ref)
        if not discard:
            self._save_possible_edits(doc)
        self._changed(doc)
        self._call("Close", doc.Close)

    # --- input tables -----------------------------------------------------------------

    def table_kind(self, name: str) -> int:
        key = name[len(TABLE_PREFIX) :] if name.startswith(TABLE_PREFIX) else name
        for k, v in self.table_kinds.items():
            if k.lower() == key.lower():
                return v
        raise LiraInputError(
            f"Unknown input table {name!r}. Known tables: {', '.join(sorted(self.table_kinds))}"
        )

    def _table(self, doc: Any, name: str, numbers: list[int] | None) -> Any:
        kind = self.table_kind(name)
        if numbers:
            part, pars = self._c.kLiraModelPart_FromArray, [int(n) for n in numbers]
        else:
            part, pars = self._c.kLiraModelPart_All, None
        item = self._call(
            f"create table {name}",
            doc.AllTables.CreateNewItem,
            kind,
            pars,
            part,
            f"{TEMP_TABLE_MARK}{uuid.uuid4().hex[:8]}",
            -1,
        )
        return self._cast(item, "ILiraTable")

    def _drop_table(self, doc: Any, table: Any) -> None:
        """Input tables created through the API stay in the document; remove ours.

        Called from ``finally``: a failure here is logged, never raised, so it cannot hide
        the error of the table operation itself.
        """
        mark = ""
        try:
            mark = str(table.Name)
            tables = doc.AllTables
            for i in range(tables.ItemCount - 1, -1, -1):
                if str(tables.Item(i).Name) == mark:
                    tables.Delete(i)
                    return
        except Exception as exc:
            log.warning("Could not remove scratch table %r: %s", mark, com_message(exc))

    def read_table(self, ref: str, name: str, numbers: list[int] | None = None) -> list[list]:
        doc = self.find_document(ref)
        with self._reading(doc):
            table = self._table(doc, name, numbers)
            try:
                data = self._call(f"read table {name}", table.GetContents, [])
            finally:
                self._drop_table(doc, table)
        return normalize_rows(data)

    def write_table(
        self, ref: str, name: str, rows: list[list], numbers: list[int] | None = None
    ) -> list[TableError]:
        """Replace the rows of a table (for ``numbers`` only, if given) and apply them."""
        doc = self.find_document(ref)
        self._changed(doc)
        table = self._table(doc, name, numbers)
        try:
            data = [["" if cell is None else cell for cell in row] for row in rows]
            self._call(f"fill table {name}", table.SetContents, data)
            ok, errs = self._call(f"apply table {name}", table.Apply)
        finally:
            self._drop_table(doc, table)
        errors = parse_table_errors(str(errs or ""))
        if not ok and not errors:
            errors = [TableError(-1, -1, "LIRA rejected the table without details")]
        return errors

    def self_weight(
        self, ref: str, load_case: int, factor: float, elements: list[int] | None = None
    ) -> str:
        """Add self weight loads (of elements whose sections have a density) to a load
        case, which LIRA creates if needed; only ``elements`` if given. Returns LIRA's
        message, if any."""
        doc = self.find_document(ref)
        self._changed(doc)
        doc.CurrentLoadCase = load_case
        if not elements:
            return str(self._call("SetDeadWeightLoad", doc.SetDeadWeightLoad, DEAD_ALL, factor))
        # LIRA adds to the selection: clear it first, or the user's selection gets loads too.
        # The user's element selection in LIRA's window is therefore lost.
        self._call("Unselect", doc.Unselect, "all", SEL_ELEMENTS)
        self._call("Select", doc.Select, " ".join(map(str, elements)), SEL_ELEMENTS)
        try:
            return str(
                self._call("SetDeadWeightLoad", doc.SetDeadWeightLoad, DEAD_SELECTED, factor)
            )
        finally:
            try:
                self._call("Unselect", doc.Unselect, "all", SEL_ELEMENTS)
            except LiraComError:
                log.warning("Could not clear the selection after adding self weight")

    def model_picture(self, ref: str, view: str = "isometric") -> bytes:
        """A PNG of the model as LIRA's view window shows it, in the given projection
        (or the current one) and fitted to the window."""
        import win32gui

        from lira_sapr_mcp.adapters.picture import capture_window, crop, encode_png

        if view not in VIEWS:
            raise LiraInputError(f"Unknown view {view!r}; use one of {sorted(VIEWS)}")
        doc = self.find_document(ref)
        self._call("Activate", doc.Activate)
        for cmd in (VIEWS[view], FIT_IN_WINDOW):
            if cmd:
                self._call("StartCmd", self._app.StartCmd, cmd)
                self._settle(0.6)  # LIRA redraws after handling its window messages
        frame = self._view_window(doc)
        if win32gui.IsIconic(win32gui.GetAncestor(frame, 2)):  # GA_ROOT
            raise LiraInputError("LIRA's window is minimized: restore it to take a picture")
        try:
            return encode_png(*crop(*capture_window(frame)))
        except ValueError as exc:
            raise LiraComError(f"Could not take a picture of {doc.Title}: {exc}") from exc

    def _view_window(self, doc: Any) -> int:
        """The largest drawing window inside the document's window in LIRA's MDI area."""
        import win32gui

        from lira_sapr_mcp.adapters.dialogs import Win32Windows

        names = {Path(str(doc.PathName)).name.lower(), str(doc.Title).lower()}
        windows = Win32Windows()
        for top in windows.top_level(Path(self.install.exe).name):
            for mdi in windows.children(top):
                if win32gui.GetClassName(mdi) != "MDIClient":
                    continue
                for frame in windows.children(mdi):
                    text = win32gui.GetWindowText(frame).lower()
                    if win32gui.GetParent(frame) == mdi and any(n and n in text for n in names):
                        inner = windows.children(frame) or [frame]
                        return max(inner, key=lambda h: _area(win32gui.GetClientRect(h)))
        raise LiraComError(f"LIRA shows no window of {doc.Title}")

    def _settle(self, seconds: float) -> None:
        import pythoncom

        end = time.monotonic() + seconds
        while time.monotonic() < end:
            pythoncom.PumpWaitingMessages()
            time.sleep(0.05)

    def run_script(self, code: str, ref: str | None, timeout_s: float) -> dict[str, Any]:
        """Run the agent's Python code with LIRA's objects (see services/scripts.py)."""
        from lira_sapr_mcp.services.scripts import run_script

        self.connect()
        doc = self.find_document(ref) if ref else self._app.ActiveDocument
        if doc is not None:
            self._changed(doc)  # the script may change it: never treat it as only read
        names = {"lira": self._app, "doc": doc, "adapter": self, "constants": self._c}
        try:
            return run_script(code, names, timeout_s)
        finally:
            del doc, names

    def delete_self_weight(self, ref: str) -> str:
        doc = self.find_document(ref)
        self._changed(doc)
        return str(self._call("SetDeadWeightLoad", doc.SetDeadWeightLoad, DEAD_DELETE, 1.0))

    # --- text format ----------------------------------------------------------------

    def directories(self) -> dict[str, str]:
        return lira_directories(self.install.year)

    def export_text(self, ref: str, timeout_s: float = 120.0) -> str:
        """The model in LIRA's text format, via the menu command "Create text file".

        LIRA writes ``<text data folder>/<title>.txt``. A file of the same name that was
        already there is set aside and put back afterwards.
        """
        doc = self.find_document(ref)
        with self._reading(doc):
            return self._export_text(doc, timeout_s)

    def _export_text(self, doc: Any, timeout_s: float) -> str:
        import pythoncom

        doc.Activate()
        dirs = self.directories()
        folder = dirs.get("TextDataDirectory") or dirs.get("DataDirectory")
        if not folder:
            raise LiraComError("LIRA's data folder is not set in its settings (registry)")
        target = Path(folder) / f"{doc.Title}.txt"
        parked = None
        if target.exists():
            parked = target.with_name(f"{target.name}.{TEMP_TABLE_MARK}{uuid.uuid4().hex[:8]}")
            target.rename(parked)
        try:
            cmd = EXPORT_TEXT_CMD.get(self.install.year, EXPORT_TEXT_CMD[2024])
            self._call("StartCmd(Create text file)", self._app.StartCmd, cmd)
            deadline = time.monotonic() + timeout_s
            last_size = -1
            while True:
                pythoncom.PumpWaitingMessages()
                if target.exists():
                    size = target.stat().st_size
                    if size > 0 and size == last_size:
                        break
                    last_size = size
                if time.monotonic() > deadline:
                    raise LiraComError(
                        f"LIRA did not write the text export {target} within {timeout_s:.0f} s"
                    )
                time.sleep(0.2)
            raw = target.read_bytes()
        finally:
            target.unlink(missing_ok=True)
            if parked is not None:
                parked.rename(target)
        text = decode_lira_text(raw)
        if text is None:
            raise LiraComError(f"Cannot decode LIRA's text export {target}")
        return text

    # --- analysis -------------------------------------------------------------------

    def start_analysis(self, ref: str) -> dict:
        """Start analysing a saved model; returns at once (progress comes as events)."""
        info = self.document_info(ref)
        if not info.saved:
            raise LiraInputError("Save the model to a .lir file before the analysis")
        if info.modified:
            raise LiraInputError(
                f"{info.title} has unsaved changes; LIRA analyses the file on disk: save first"
            )
        if self.analysis.status in ("running", "needs_user"):
            raise LiraInputError(f"An analysis of {self.analysis.model} is still running")
        self._save_possible_edits(self.find_document(info.path))
        self.analysis.start(info.path)
        try:
            ok = self._call("StartAnalysis", self._app.StartAnalysis, info.path)
        except BaseException:
            self.analysis.on_finished(1)
            raise
        if not ok:
            self.analysis.on_finished(1)
            work = self.directories().get("WorkDirectory", "")
            log_text = read_protocol(Path(work) / "PackageAnalysisLog.TXT") or ""
            raise LiraComError(f"LIRA refused to start the analysis. {log_text.strip()}")
        return self.analysis.as_dict()

    def analysis_status(self) -> dict:
        status = self.analysis.as_dict()
        if self.analysis.done and self.analysis.model:
            text = self.protocol(self.analysis.model)
            if text is not None:
                status["protocol"] = summarize_protocol(text)
            status["model_closed_by_lira"] = not any(
                norm_path(str(d.PathName)) == norm_path(self.analysis.model) for d in self._docs()
            )
        return status

    def stop_analysis(self) -> None:
        self._call("StopAnalysis", self._app.StopAnalysis)

    def results_info(self, model_path: str) -> dict[str, Any]:
        """Whether LIRA keeps analysis results under this model's name, their size and time.

        LIRA keeps them in its work folder by model name only, so they may belong to an
        older version of the model or to another model of the same name. The model file's
        time cannot tell: the server saves models it only read (see _save_possible_edits).
        """
        main = self.results.main_data(model_path)
        if main is None:
            return {"present": False}
        info: dict[str, Any] = {"present": True, **main}
        work = self.directories().get("WorkDirectory")
        stem = Path(model_path).stem
        marker = Path(work) / f"{stem}#00.{stem}" if work else None
        if marker and marker.exists():
            written = datetime.fromtimestamp(marker.stat().st_mtime)
            info["written"] = written.isoformat(timespec="seconds")
        return info

    def delete_results(self, model_path: str) -> None:
        if (
            self.analysis.status in ("running", "needs_user")
            and self.analysis.model
            and (norm_path(self.analysis.model) == norm_path(model_path))
        ):
            raise LiraInputError(f"The analysis of {model_path} is still running")
        self._call("DeleteResults", self._app.DeleteResults, model_path)

    def protocol(self, model_path: str) -> str | None:
        work = self.directories().get("WorkDirectory")
        return read_protocol(protocol_path(work, model_path)) if work else None

    # --- results --------------------------------------------------------------------

    def node_displacements(
        self, model_path: str, nodes: list[int] | None, cases: list[int] | None
    ) -> list[dict]:
        return self.results.node_displacements(model_path, nodes, cases)

    def element_forces(
        self,
        model_path: str,
        elements: list[int] | None,
        cases: list[int] | None,
        families: list[str] | None = None,
    ) -> list[dict]:
        return self.results.element_forces(model_path, elements, cases, families)

    def load_combinations(self, model_path: str) -> dict[str, Any]:
        return self.results.load_combinations(model_path)

    def combination_displacements(
        self, model_path: str, nodes: list[int] | None, combinations: list[int] | None
    ) -> list[dict]:
        return self.results.combination_displacements(model_path, nodes, combinations)

    def combination_forces(
        self,
        model_path: str,
        elements: list[int] | None,
        combinations: list[int] | None,
        families: list[str] | None = None,
        limit_states: list[int] | None = None,
    ) -> list[dict]:
        return self.results.combination_forces(
            model_path, elements, combinations, families, limit_states
        )

    def design_forces(
        self,
        model_path: str,
        elements: list[int] | None,
        families: list[str] | None = None,
        limit_states: list[int] | None = None,
    ) -> list[dict]:
        return self.results.design_forces(model_path, elements, families, limit_states)

    def periods(self, model_path: str, cases: list[int] | None) -> list[dict]:
        return self.results.periods(model_path, cases)

    def reinforcement(
        self, model_path: str, elements: list[int] | None, design_option: int = 1
    ) -> list[dict]:
        return self.results.reinforcement(model_path, elements, design_option)

    def fragment_loads(
        self, model_path: str, nodes: list[int] | None, cases: list[int] | None
    ) -> list[dict]:
        return self.results.fragment_loads(model_path, nodes, cases)

    def punching_loads(
        self, model_path: str, nodes: list[int] | None, cases: list[int] | None
    ) -> list[dict]:
        return self.results.punching_loads(model_path, nodes, cases)

    # --- units ----------------------------------------------------------------------

    def units(self) -> Units:
        self.connect()
        u = self._app.MeasurementUnits

        def n(kind: str, value: int) -> str:
            names = UNIT_NAMES[kind]
            return names[value] if 0 <= value < len(names) else "none"

        return Units(
            geometry=n("geometry", u.Geometry),
            sections=n("geometry", u.Sections),
            loads=n("force", u.Loads1),
            loads_per=n("geometry", u.Loads2),
            materials=n("stress", u.MaterialProperties1),
            materials_per=n("geometry", u.MaterialProperties2),
            displacements=n("geometry", u.Displacements),
            forces=n("force", u.Forces1),
            forces_per=n("geometry", u.Forces2),
            stresses=n("stress", u.Stresses1),
            stresses_per=n("geometry", u.Stresses2),
            temperature=n("temperature", u.Temperature),
        )


def return_parked_files(folder: Path) -> list[Path]:
    """Put back the user's text files that a text export set aside and a crash left
    renamed (``<name>.txt.lira-mcp-<id>``). A file whose name is taken again is left as
    it is and logged."""
    returned = []
    for parked in folder.glob(f"*.{TEMP_TABLE_MARK}*"):
        original = parked.with_name(parked.name.split(f".{TEMP_TABLE_MARK}")[0])
        if original.exists():
            log.warning("Parked file %s not returned: %s exists again", parked, original.name)
            continue
        try:
            parked.rename(original)
            returned.append(original)
            log.warning("Returned the parked file %s", original)
        except OSError as exc:
            log.warning("Could not return the parked file %s: %s", parked, exc)
    return returned


def _area(rect: tuple[int, int, int, int]) -> int:
    return (rect[2] - rect[0]) * (rect[3] - rect[1])
