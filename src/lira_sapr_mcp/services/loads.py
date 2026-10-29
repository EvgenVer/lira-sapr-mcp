"""Loads through LIRA's text format (the COM API has no input table for loads).

Everything here runs on the COM thread.

- Reading: export the model as text and parse documents 6 and 7.
- New model: write the agent's text to a temporary file and import it.
- Changing loads of an existing model: export, replace the loads, import the text as a
  new document, copy every input table back from the original (the import loses some,
  e.g. load case kinds and structural blocks), check that tables and loads are as
  intended, and only then replace the original file. If any check fails, the original
  model stays untouched.
"""

import logging
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from lira_sapr_mcp.errors import LiraError, LiraInputError
from lira_sapr_mcp.services.textformat import Load, TextModel

log = logging.getLogger(__name__)


def load_dicts(loads: list[Load]) -> list[dict[str, Any]]:
    return [asdict(ld) | {"on_node": ld.on_node} for ld in loads]


def read_loads(adapter: Any, ref: str, cases: list[int] | None = None) -> list[dict]:
    loads = TextModel.parse(adapter.export_text(ref)).loads()
    return load_dicts([ld for ld in loads if cases is None or ld.case in cases])


def _import_text(adapter: Any, text: str, title: str) -> Any:
    folder = Path(tempfile.mkdtemp(prefix="lira-mcp-"))
    try:
        src = folder / f"{title}.txt"
        src.write_text(text, encoding="utf-8-sig")
        return adapter.import_file(str(src))
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def import_text_model(adapter: Any, text: str, save_as: str) -> Any:
    target = Path(save_as)
    if target.suffix.lower() != ".lir":
        raise LiraInputError("save_as must be a .lir path")
    TextModel.parse(text)  # fail early on text that is not a LIRA text model
    info = _import_text(adapter, text, target.stem)
    ref = info.path or info.title
    try:
        return adapter.save_document(ref, str(target))
    except BaseException:
        adapter.close_document(ref, discard=True)
        raise


def _snapshot(adapter: Any, ref: str) -> dict[str, list | None]:
    tables: dict[str, list | None] = {}
    for name in sorted(adapter.table_kinds):
        try:
            tables[name] = adapter.read_table(ref, name)
        except LiraError:
            tables[name] = None  # LIRA cannot build this table for this model
    return tables


def _same_loads(a: list[Load], b: list[Load]) -> bool:
    def key(ld: Load) -> tuple:
        values = [round(v, 9) for v in ld.values]
        while values and values[-1] == 0:  # LIRA pads value rows with zeros on export
            values.pop()
        return (ld.case, ld.target, ld.type, ld.direction, tuple(values))

    return sorted(map(key, a)) == sorted(map(key, b))


def _changed_kinds(before: list, now: list) -> list[str]:
    """Load case kinds (column 4 of LoadCases) that differ after the rebuild, as 'old -> new'.

    The text keeps kinds as SNiP-style codes and the import reads them in LIRA's default
    combination norms (SP 20.13330), so every rebuild scrambles them. Writing LoadCases
    back restores them only when the model uses those norms: LIRA maps the written names
    into the dictionary of the default norms. Rows without a kind on either side are left to
    the full check.
    """
    old = {row[0]: row[3] for row in before if len(row) > 3}
    return [
        f"{row[0]}: {old[row[0]]} -> {row[3]}"
        for row in now
        if len(row) > 3 and row[3] is not None and old.get(row[0]) not in (None, row[3])
    ]


def set_loads(adapter: Any, ref: str, loads: list[Load], cases: list[int] | None) -> dict[str, Any]:
    """Replace the loads of ``cases`` (all cases when None) in a saved model."""
    orig = adapter.document_info(ref)
    if not orig.saved:
        raise LiraInputError("Save the model to a .lir file before changing its loads")
    if orig.modified:
        raise LiraInputError(f"{orig.title} has unsaved changes: save it first")
    model = TextModel.parse(adapter.export_text(orig.path))
    if cases is not None:
        stray = sorted({ld.case for ld in loads} - set(cases))
        if stray:
            raise LiraInputError(f"Loads for load cases {stray} are outside load_cases={cases}")
    kept = [ld for ld in model.loads() if cases is not None and ld.case not in cases]
    wanted = kept + loads
    model.set_loads(wanted)
    before = _snapshot(adapter, orig.path)

    new = _import_text(adapter, model.render(), orig.title)
    new_ref = new.path or new.title
    try:
        restored, failed = [], {}
        for name, rows in before.items():
            if rows is None:
                continue
            try:
                now = adapter.read_table(new_ref, name)
            except LiraError:
                now = None
            if now != rows:
                try:
                    errors = [e.message for e in adapter.write_table(new_ref, name, rows)]
                except LiraError as exc:  # LIRA refuses the whole table, e.g. LoadCases
                    errors = [str(exc)]  # of a model with construction stages
                if errors:
                    failed[name] = errors[:5]
                restored.append(name)
        after = _snapshot(adapter, new_ref)
        # A table LIRA cannot build or refused to take is left to the full check below.
        if "LoadCases" not in failed and None not in (
            before.get("LoadCases"),
            after.get("LoadCases"),
        ):
            kinds = _changed_kinds(before["LoadCases"], after["LoadCases"])
            if kinds:
                raise LiraError(
                    "Loads were not changed: this model uses combination norms other than "
                    "LIRA's default ones (SP 20.13330), and a model rebuilt from text gets "
                    f"the default norms, so its load case kinds would change ({'; '.join(kinds)}"
                    "). LIRA 2024 R2's API cannot keep other norms; change these loads in "
                    "LIRA itself. The original model is untouched."
                )
        differs = [n for n, rows in before.items() if rows is not None and after.get(n) != rows]
        got = TextModel.parse(adapter.export_text(new_ref)).loads()
        if differs or failed or not _same_loads(got, wanted):
            raise LiraError(
                "Loads were not changed: the rebuilt model did not match the original "
                f"(tables differing: {differs or 'none'}; restore errors: {failed or 'none'}; "
                f"loads match: {_same_loads(got, wanted)}). The original model is untouched."
            )
    except BaseException:
        try:
            adapter.close_document(new_ref, discard=True)
        except LiraError:
            log.warning("could not close the rebuilt model %s", new_ref, exc_info=True)
        raise
    adapter.close_document(orig.path, discard=True)
    adapter.save_document(new_ref, orig.path)
    log.info("loads of %s replaced; tables restored: %s", orig.path, restored)
    return {
        "model": orig.path,
        "loads_now": len(wanted),
        "load_cases_changed": cases if cases is not None else "all",
        "tables_restored_after_import": restored,
        "checked": "all input tables equal the original; loads equal the request",
    }
