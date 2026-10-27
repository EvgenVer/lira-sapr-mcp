"""High-level model edits built on input tables (run on the COM thread).

Each operation checks its arguments against the model first, then writes only the rows
it changes; LIRA validates them and on any error leaves the model unchanged.
"""

import re
from typing import Any

from lira_sapr_mcp.adapters.base import TableError
from lira_sapr_mcp.errors import LiraInputError

DIRECTIONS = ("X", "Y", "Z", "UX", "UY", "UZ")
# Section values that LIRA derives from the section size; -1 makes it derive them again.
DERIVED = ("EF", "EIy", "EIz", "GIk", "GFz", "GFy")


class TableRejected(LiraInputError):
    def __init__(self, table: str, errors: list[TableError]) -> None:
        details = "; ".join(f"row {e.row}, column {e.column}: {e.text}" for e in errors)
        super().__init__(f"LIRA rejected {table}: {details}")


def _write(adapter: Any, ref: str, table: str, rows: list[list], numbers: list[int] | None) -> None:
    errors = adapter.write_table(ref, table, rows, numbers)
    if errors:
        raise TableRejected(table, errors)


def _numbers(adapter: Any, ref: str, table: str) -> set[int]:
    return {int(row[0]) for row in adapter.read_table(ref, table) if row and row[0] is not None}


def _missing(wanted: list[int], present: set[int], what: str) -> None:
    absent = sorted(set(wanted) - present)
    if absent:
        raise LiraInputError(f"No {what} {', '.join(map(str, absent[:20]))} in the model")


def add_nodes(adapter: Any, ref: str, coordinates: list[list[float]]) -> list[int]:
    """Append nodes after the last one; returns their numbers."""
    if not coordinates or any(len(c) != 3 for c in coordinates):
        raise LiraInputError("coordinates: a list of [X, Y, Z]")
    first = max(_numbers(adapter, ref, "Nodes_Coordinates"), default=0) + 1
    numbers = list(range(first, first + len(coordinates)))
    rows = [[n, *map(float, c)] for n, c in zip(numbers, coordinates, strict=True)]
    _write(adapter, ref, "Nodes_Coordinates", rows, numbers)
    return numbers


def add_elements(
    adapter: Any, ref: str, fe_type: int, nodes: list[list[int]], stiffness: int | None
) -> list[int]:
    """Append elements of one FE type after the last one; returns their numbers."""
    if not nodes or any(len(n) < 2 for n in nodes):
        raise LiraInputError("nodes: a list of node lists, one per element, e.g. [[1, 2]]")
    _missing([n for el in nodes for n in el], _numbers(adapter, ref, "Nodes_Coordinates"), "nodes")
    if stiffness is not None:
        _missing([stiffness], _numbers(adapter, ref, "Stiffnesses"), "stiffness")
    first = max(_numbers(adapter, ref, "Elements_TypeAndNodes"), default=0) + 1
    numbers = list(range(first, first + len(nodes)))
    rows = [[e, fe_type, ", ".join(map(str, n))] for e, n in zip(numbers, nodes, strict=True)]
    _write(adapter, ref, "Elements_TypeAndNodes", rows, numbers)
    if stiffness is not None:
        _write(adapter, ref, "Elements_Stiffnesses", [[e, stiffness] for e in numbers], numbers)
    return numbers


def set_stiffness(adapter: Any, ref: str, elements: list[int], stiffness: int) -> None:
    """Assign a stiffness to elements.

    Not Stiffnesses_Factors: a factor there does not change a linear analysis (T14).
    """
    _missing(elements, _numbers(adapter, ref, "Elements_TypeAndNodes"), "elements")
    _missing([stiffness], _numbers(adapter, ref, "Stiffnesses"), "stiffness")
    _write(adapter, ref, "Elements_Stiffnesses", [[e, stiffness] for e in elements], elements)


def copy_stiffness(adapter: Any, ref: str, source: int, changes: dict[str, float]) -> int:
    """A new stiffness: a copy of ``source`` with some parameters changed (e.g. B, H, E,
    Ro as LIRA names them in the Stiffnesses table). Returns its number."""
    rows = adapter.read_table(ref, "Stiffnesses")
    row = next((list(r) for r in rows if r and r[0] == source), None)
    if row is None:
        raise LiraInputError(f"No stiffness {source} in the model")
    text = str(row[4] or "")
    for name, value in changes.items():
        pattern = re.compile(rf"(?<![\w]){re.escape(name)}:[^\s,]+")
        if not pattern.search(text):
            have = sorted(set(re.findall(r"(?<![\w])(\w+):", text)) - set(DERIVED))
            raise LiraInputError(f"Stiffness {source} has no parameter {name!r}; it has {have}")
        text = pattern.sub(f"{name}:{value:.12g}", text)
    for name in DERIVED:
        text = re.sub(rf"(?<![\w]){name}:[^\s,]+", f"{name}:-1", text)
    number = max(int(r[0]) for r in rows) + 1
    row[0], row[4] = number, text
    _write(adapter, ref, "Stiffnesses", [*rows, row], None)
    return number


def set_restraints(adapter: Any, ref: str, nodes: list[int], directions: list[str]) -> None:
    """Fix the given directions of nodes and free the others (empty list: free node)."""
    wanted = [d.upper() for d in directions]
    unknown = sorted(set(wanted) - set(DIRECTIONS))
    if unknown:
        raise LiraInputError(f"Unknown directions {unknown}; use {list(DIRECTIONS)}")
    _missing(nodes, _numbers(adapter, ref, "Nodes_Coordinates"), "nodes")
    flags = [1 if d in wanted else None for d in DIRECTIONS]
    _write(adapter, ref, "Nodes_Restraints", [[n, *flags, None] for n in nodes], nodes)
