"""Helpers shared by the tool modules."""

import functools
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

from mcp.server.mcpserver.exceptions import ToolError

from lira_sapr_mcp.errors import LiraError

P = ParamSpec("P")
R = TypeVar("R")


def lira_errors(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Report LIRA errors to the agent as plain tool errors instead of tracebacks."""

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await fn(*args, **kwargs)
        except LiraError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


def plain(obj: Any) -> Any:
    """Dataclasses to dicts, recursively, for structured tool output."""
    from dataclasses import asdict, is_dataclass

    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, list | tuple):
        return [plain(x) for x in obj]
    if isinstance(obj, dict):
        return {k: plain(v) for k, v in obj.items()}
    return obj
