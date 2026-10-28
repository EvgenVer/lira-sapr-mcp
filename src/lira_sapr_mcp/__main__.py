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
    args = sys.argv[1:]
    if "--version" in args:
        print(f"lira-sapr-mcp {__version__}")
        return
    if "--diagnose" in args:
        from pathlib import Path

        from lira_sapr_mcp.diagnose import write_report

        rest = args[args.index("--diagnose") + 1 :]
        print(f"Report written to {write_report(Path(rest[0]) if rest else None)}")
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
    scripts = "--no-scripts" not in args
    logging.getLogger(__name__).info("scripts %s", "on" if scripts else "off (--no-scripts)")
    build_server(LiraSession(settings), scripts=scripts).run("stdio")


if __name__ == "__main__":
    main()
