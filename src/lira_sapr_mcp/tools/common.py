"""Helpers shared by the tool modules."""

import functools
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from lira_sapr_mcp.errors import LiraError, LiraInputError

READ_ONLY = ToolAnnotations(readOnlyHint=True)

# LIRA API functions each tool needs, filled by ``needs``: lira_status lists the tools a
# connected LIRA release cannot run.
REQUIRES: dict[str, tuple[str, ...]] = {}


def lira_errors[**P, R](fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
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


async def backup_before_change(session: Any, ref: str) -> str | None:
    """Back up a saved model before the session first changes it; the backup's path."""
    info = await session.run(session.adapter.document_info, ref)
    if not info.saved:
        return None
    backup = session.backups.ensure(info.path)
    return str(backup) if backup else None


# --8<-- [start:needs]
def needs(session: Any, *capabilities: str) -> Callable[[Callable[..., Awaitable[Any]]], Any]:
    """Refuse a tool clearly when this LIRA release lacks an API function it needs."""

    def wrap[**P, R](fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        REQUIRES[fn.__name__] = capabilities

        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            adapter = session.adapter
            if not adapter.connected:
                await session.run(adapter.connect)
            missing = [c for c in capabilities if c not in adapter.capabilities]
            if missing:
                raise LiraInputError(
                    f"{fn.__name__} needs {', '.join(missing)} of LIRA's API, which LIRA "
                    f"{session.install.year} does not have"
                )
            return await fn(*args, **kwargs)

        return wrapper

    return wrap


# --8<-- [end:needs]


def unavailable_tools(capabilities: frozenset[str]) -> list[str]:
    return sorted(t for t, caps in REQUIRES.items() if not set(caps) <= capabilities)
