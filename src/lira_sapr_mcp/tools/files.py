"""Tools: LIRA status, opening, creating, saving and closing models, model summary."""

from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from lira_sapr_mcp.adapters.base import MODEL_TYPES
from lira_sapr_mcp.errors import LiraInputError
from lira_sapr_mcp.services.models import model_summary
from lira_sapr_mcp.services.session import LiraSession
from lira_sapr_mcp.tools.common import lira_errors, plain

READ_ONLY = ToolAnnotations(readOnlyHint=True)


def register(mcp: MCPServer, session: LiraSession) -> None:
    @mcp.tool(annotations=READ_ONLY)
    @lira_errors
    async def lira_status() -> dict[str, Any]:
        """Installed LIRA versions, the one this server uses, and whether it is connected.

        When connected, also lists the API capabilities and input table names of that
        LIRA release. Does not start LIRA.
        """
        return session.status()

    @mcp.tool(annotations=READ_ONLY)
    @lira_errors
    async def lira_list_models() -> list[dict[str, Any]]:
        """Models open in LIRA now: title, file path, model type, unsaved changes, active."""
        return plain(await session.run(session.adapter.list_documents))

    @mcp.tool()
    @lira_errors
    async def lira_open_model(path: str) -> dict[str, Any]:
        """Open a .lir model file in LIRA (starts LIRA if needed) and make it active."""
        info, messages = await session.run(session.adapter.open_document, path)
        return {"model": plain(info), "lira_messages": messages}

    @mcp.tool()
    @lira_errors
    async def lira_create_model(
        title: str, model_type: int = 5, description: str = "", save_as: str | None = None
    ) -> dict[str, Any]:
        """Create an empty model.

        model_type is LIRA's system label (degrees of freedom per node):
        1 = 2D XOZ truss (X, Z); 2 = 2D XOZ frame (X, Z, UY); 3 = grillage/plate XOY
        (Z, UX, UY); 4 = 3D truss (X, Y, Z); 5 = general 3D (X, Y, Z, UX, UY, UZ).
        title: up to 30 characters, no , . < > ( ) # ? * | \\ / :
        save_as: optional .lir path to save the new model to right away.
        """
        if model_type not in MODEL_TYPES and model_type not in (6, 15):
            raise LiraInputError(f"Unknown model_type {model_type}")
        info = await session.run(session.adapter.create_document, title, model_type, description)
        if save_as:
            ref = info.path or info.title
            info = await session.run(session.adapter.save_document, ref, save_as)
        return {"model": plain(info)}

    @mcp.tool()
    @lira_errors
    async def lira_save_model(
        model: str | None = None, save_as: str | None = None
    ) -> dict[str, Any]:
        """Save a model (default: the active one). save_as: new .lir path ("Save as").

        Before overwriting an existing file for the first time in this session the server
        copies it into a backup folder next to the model; the result names the copy.
        """
        ref = await session.resolve(model)
        target = save_as or ref
        backup = session.backups.ensure(target) if Path(target).is_file() else None
        info = await session.run(session.adapter.save_document, ref, save_as)
        return {"model": plain(info), "backup": str(backup) if backup else None}

    @mcp.tool()
    @lira_errors
    async def lira_close_model(
        model: str | None = None, discard_changes: bool = False
    ) -> dict[str, Any]:
        """Close a model (default: the active one).

        Refuses to close a model with unsaved changes unless discard_changes is true.
        """
        ref = await session.resolve(model)
        info = await session.run(session.adapter.document_info, ref)
        if info.modified and not discard_changes:
            raise LiraInputError(
                f"{info.title} has unsaved changes: save it first or pass discard_changes=true"
            )
        await session.run(session.adapter.close_document, ref)
        return {"closed": plain(info)}

    @mcp.tool(annotations=READ_ONLY)
    @lira_errors
    async def lira_model_summary(model: str | None = None) -> dict[str, Any]:
        """Overview of a model (default: the active one): model type, LIRA's current input
        units, number of nodes and elements, elements per finite element type, stiffnesses
        and load cases. Start here before reading or changing a model.
        """
        ref = await session.resolve(model)
        return await session.run(model_summary, session.adapter, ref)
