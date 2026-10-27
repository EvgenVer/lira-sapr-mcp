"""Tools: LIRA input tables and loads."""

import re
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from lira_sapr_mcp.errors import LiraInputError
from lira_sapr_mcp.services import loads as loads_service
from lira_sapr_mcp.services.session import LiraSession
from lira_sapr_mcp.services.textformat import Load
from lira_sapr_mcp.tools.common import lira_errors, plain

READ_ONLY = ToolAnnotations(readOnlyHint=True)
Cell = str | int | float | None


def parse_numbers(numbers: list[int] | str | None) -> list[int] | None:
    """Accept [1, 2, 5] or LIRA-style "1-3 7 10-12"."""
    if numbers is None or isinstance(numbers, list):
        return numbers or None
    out: list[int] = []
    for part in re.split(r"[,\s]+", numbers.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)-(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if b < a or b - a > 1_000_000:
                raise LiraInputError(f"Bad range {part!r}")
            out.extend(range(a, b + 1))
        elif part.isdigit():
            out.append(int(part))
        else:
            raise LiraInputError(f"Bad number list {numbers!r}: use e.g. '1-3 7 10-12'")
    return out or None


def register(mcp: MCPServer, session: LiraSession) -> None:
    async def backup_before_change(ref: str) -> str | None:
        info = await session.run(session.adapter.document_info, ref)
        if not info.saved:
            return None
        backup = session.backups.ensure(info.path)
        return str(backup) if backup else None

    @mcp.tool(annotations=READ_ONLY)
    @lira_errors
    async def lira_list_input_tables() -> list[str]:
        """Names of the input tables this LIRA release supports (starts LIRA if needed).

        Typical: Nodes_Coordinates (number, X, Y, Z), Elements_TypeAndNodes (number,
        FE type, "node, node, ..."), Nodes_Restraints (node + 6 flags X Y Z UX UY UZ),
        Stiffnesses, Elements_Stiffnesses (element, stiffness number), LoadCases, DCL.
        Read a table first to see its columns and value format.
        """
        await session.run(session.adapter.connect)
        return sorted(session.adapter.table_kinds)

    @mcp.tool(annotations=READ_ONLY)
    @lira_errors
    async def lira_read_table(
        table: str,
        model: str | None = None,
        numbers: list[int] | str | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Rows of an input table (default model: the active one).

        numbers: only these nodes/elements, as a list or "1-10 15". Values use LIRA's
        current units (see lira_model_summary). Empty cells are null. Large tables are
        paged with offset/limit; the result says how many rows there are in total.
        """
        ref = await session.resolve(model)
        rows = await session.run(session.adapter.read_table, ref, table, parse_numbers(numbers))
        page = rows[offset : offset + max(1, min(limit, 5000))]
        return {"table": table, "total_rows": len(rows), "offset": offset, "rows": page}

    @mcp.tool()
    @lira_errors
    async def lira_write_table(
        table: str,
        rows: list[list[Cell]],
        model: str | None = None,
        numbers: list[int] | str | None = None,
    ) -> dict[str, Any]:
        """Write rows into an input table and apply them to the model.

        Without numbers the rows replace the whole table: rows with new numbers add
        objects (e.g. nodes). With numbers only those objects' rows are replaced.
        LIRA checks the rows; on any error nothing changes and the errors are returned
        with 0-based row/column. The model file is backed up before its first change.
        """
        ref = await session.resolve(model)
        backup = await backup_before_change(ref)
        errors = await session.run(
            session.adapter.write_table, ref, table, rows, parse_numbers(numbers)
        )
        return {"applied": not errors, "errors": plain(errors), "backup": backup}

    @mcp.tool(annotations=READ_ONLY)
    @lira_errors
    async def lira_read_loads(
        model: str | None = None, load_cases: list[int] | None = None
    ) -> dict[str, Any]:
        """Loads of a model, from LIRA's text export.

        Each load: case, target (node number if on_node, else element number), type
        (LIRA load type code; 0 = nodal force/moment, 6 = uniform load on a bar),
        direction (1 X, 2 Y, 3 Z; nodal moments 4 UX, 5 UY, 6 UZ), values (in the
        units of the text format, see the model's document 0 key 33).
        """
        ref = await session.resolve(model)
        loads = await session.run(loads_service.read_loads, session.adapter, ref, load_cases)
        return {"loads": loads, "count": len(loads)}

    @mcp.tool()
    @lira_errors
    async def lira_set_loads(
        loads: list[dict[str, Any]],
        model: str | None = None,
        load_cases: list[int] | None = None,
    ) -> dict[str, Any]:
        """Replace loads of a saved model: of load_cases only, or all loads when omitted.

        loads: [{case, target, type, direction, values}] as returned by lira_read_loads.
        LIRA has no API for loads, so the server rebuilds the model through LIRA's text
        format, copies every input table back, verifies tables and loads, and only then
        overwrites the file (after a backup). If verification fails, nothing changes.
        Data that is neither in input tables nor in the text format cannot be verified:
        check the model in LIRA after this call.
        """
        ref = await session.resolve(model)
        parsed = [
            Load(
                int(d["case"]),
                int(d["target"]),
                int(d["type"]),
                int(d["direction"]),
                [float(v) for v in d.get("values", [])],
            )
            for d in loads
        ]
        backup = await backup_before_change(ref)
        result = await session.run(
            loads_service.set_loads,
            session.adapter,
            ref,
            parsed,
            load_cases,
            timeout=session.settings.call_timeout_s * 5,
        )
        return result | {"backup": backup}

    @mcp.tool()
    @lira_errors
    async def lira_import_text_model(text: str, save_as: str) -> dict[str, Any]:
        """Create a model from LIRA's text input format and save it as save_as (.lir).

        The text format describes nodes, elements, stiffnesses, restraints and loads in
        numbered documents, e.g. ( 1/ elements ) ( 3/ stiffnesses ) ( 4/ coordinates )
        ( 5/ restraints ) ( 6/ loads ) ( 7/ load values ). The best way to learn it is to
        export a similar model with lira_export_text.
        """
        info = await session.run(loads_service.import_text_model, session.adapter, text, save_as)
        return {"model": plain(info)}

    @mcp.tool(annotations=READ_ONLY)
    @lira_errors
    async def lira_export_text(model: str | None = None) -> dict[str, Any]:
        """The whole model in LIRA's text input format (documents 0-8 and more)."""
        ref = await session.resolve(model)
        text = await session.run(session.adapter.export_text, ref)
        return {"text": text}
