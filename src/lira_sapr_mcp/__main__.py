"""Command-line entry point: ``lira-sapr-mcp`` runs the MCP server over stdio."""

import logging
import sys

from lira_sapr_mcp import __version__


def setup_logging(log_file) -> None:
    # stdout carries the MCP protocol in stdio mode, so the log goes to a file.
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )


def main() -> None:
    if "--version" in sys.argv[1:]:
        print(f"lira-sapr-mcp {__version__}")
        return
    from lira_sapr_mcp.config import Settings, load_settings
    from lira_sapr_mcp.errors import LiraInputError
    from lira_sapr_mcp.server import build_server
    from lira_sapr_mcp.services.session import LiraSession

    try:
        settings = load_settings()
    except LiraInputError as exc:
        # Before the server runs nobody else sees it: the default log and stderr, which
        # MCP clients show in their server logs.
        setup_logging(Settings().log_file)
        logging.getLogger(__name__).error("%s", exc)
        print(f"lira-sapr-mcp: {exc}", file=sys.stderr)
        sys.exit(2)
    setup_logging(settings.log_file)
    logging.getLogger(__name__).info("lira-sapr-mcp %s starting", __version__)
    build_server(LiraSession(settings)).run("stdio")


if __name__ == "__main__":
    main()
