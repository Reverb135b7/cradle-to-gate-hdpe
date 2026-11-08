"""Run the dashboard: ``python -m app [--port 8099]``.

For local use this defaults to ``127.0.0.1:8099``. When set, the standard
PaaS environment variables ``HOST`` and ``PORT`` take precedence, so the same
entrypoint works both locally and under a platform that injects ``$PORT``.

Note: this entrypoint is for ``python -m app``. PaaS start commands that run
``uvicorn app.server:app --host 0.0.0.0 --port $PORT`` bypass this file
entirely and rely on uvicorn's own ``--host``/``--port`` flags plus the
``$PORT`` variable they inject.
"""

from __future__ import annotations

import argparse
import os


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    parser = argparse.ArgumentParser(prog="app", description="HDPE PCF control room")
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST") or os.environ.get("PCF_APP_HOST") or "127.0.0.1",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_env_int("PORT", _env_int("PCF_APP_PORT", 8099)),
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
