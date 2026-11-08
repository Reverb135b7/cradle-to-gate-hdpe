"""Run the dashboard: ``python -m app [--port 8099]``."""

from __future__ import annotations

import argparse
import os


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    parser = argparse.ArgumentParser(prog="app", description="HDPE PCF control room")
    parser.add_argument(
        "--host", default=os.environ.get("PCF_APP_HOST", "127.0.0.1")
    )
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("PCF_APP_PORT", "8099"))
    )
    parser.add_argument("--reload", action="store_true", help="auto-reload on change")
    args = parser.parse_args(argv)

    uvicorn.run(
        "app.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
