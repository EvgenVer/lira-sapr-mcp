"""Adapter over the LIRA COM API (LiraSapr.Application and newer LiraSapphire.Application).

Every method here must run on the COM worker thread. What a given LIRA release can do is
read from its type library at connect time (``capabilities``), so new methods and input
tables of newer releases show up without code changes.
"""

import logging
import os
import uuid
from pathlib import Path
from typing import Any

from lira_sapr_mcp.adapters.base import (
    UNIT_NAMES,
    DocInfo,
    TableError,
    Units,
    normalize_rows,
    parse_table_errors,
)
from lira_sapr_mcp.adapters.discovery import LiraInstall
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
DOC_METHODS = ("SetGenerateCsvTables", "SetDeadWeightLoad", "SetSoilModel", "Select")


def com_message(exc: BaseException) -> str:
    """Readable text of a pywin32 ``com_error``."""
    args = getattr(exc, "args", ())
    if len(args) >= 3 and isinstance(args[2], tuple) and len(args[2]) >= 3 and args[2][2]:
        return str(args[2][2]).strip()
    if len(args) >= 2 and args[1]:
        return str(args[1]).strip()
    return repr(exc)


def norm_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(path)) if path else ""


class ComLiraAdapter:
    def __init__(self, install: LiraInstall) -> None:
        self.install = install
        self._app: Any = None
        self._c: Any = None
        self.capabilities: frozenset[str] = frozenset()
        self.table_kinds: dict[str, int] = {}

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
        log.info("connected to %s, capabilities: %s", self.install.progid, sorted(caps))

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

    def _info(self, doc: Any, active_path: str | None = None) -> DocInfo:
        path = str(doc.PathName or "")
        if active_path is None:
            active = self._app.ActiveDocument
            active_path = str(active.PathName) if active is not None else ""
        return DocInfo(
            title=str(doc.Title),
            path=path,
            model_type=int(doc.SystemLabel),
            modified=bool(doc.IsModified()),
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

    def open_document(self, path: str) -> tuple[DocInfo, str]:
        self.connect()
        p = Path(path)
        if not p.is_file():
            raise LiraInputError(f"File not found: {path}")
        for d in self._docs():
            if norm_path(str(d.PathName)) == norm_path(str(p)):
                d.Activate()
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
        doc.Activate()
        if path:
            target = Path(path)
            if target.suffix.lower() != ".lir":
                raise LiraInputError("LIRA models are saved with the .lir extension")
            target.parent.mkdir(parents=True, exist_ok=True)
            self._call("SaveAs", doc.SaveAs, str(target.resolve()), False)
        else:
            if not str(doc.PathName).lower().endswith(".lir"):
                raise LiraInputError("This model has never been saved: give a .lir path")
            self._call("Save", doc.Save, False)
        return self._info(doc)

    def close_document(self, ref: str) -> None:
        doc = self.find_document(ref)
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
        """Input tables created through the API stay in the document; remove ours."""
        mark = str(table.Name)
        tables = doc.AllTables
        for i in range(tables.ItemCount - 1, -1, -1):
            if str(tables.Item(i).Name) == mark:
                tables.Delete(i)
                return

    def read_table(self, ref: str, name: str, numbers: list[int] | None = None) -> list[list]:
        doc = self.find_document(ref)
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
