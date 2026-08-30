"""Development server entrypoint.

Run with:

    python run_api.py --port 8123 [--reload]

Why this exists rather than `uvicorn app.main:app`:

psycopg's async mode cannot drive Windows' default ProactorEventLoop -- every
query raises InterfaceError. Setting the loop policy at import time is not
enough, because uvicorn's asyncio setup installs its own loop afterwards and
uvicorn 0.52 has no loop_factory hook. So on Windows we create a
SelectorEventLoop ourselves and hand uvicorn a server to run inside it.

On other platforms the default loop is already compatible and uvicorn runs
normally.
"""

from __future__ import annotations

import argparse
import asyncio
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the verification API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    import uvicorn

    config = uvicorn.Config(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )

    if sys.platform == "win32" and not args.reload:
        # Own the loop so psycopg gets a Selector-based one. Incompatible with
        # --reload, which needs to supervise a subprocess; use --reload only for
        # frontend-facing iteration where the database is not exercised, or run
        # without it.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        server = uvicorn.Server(config)
        try:
            loop.run_until_complete(server.serve())
        finally:
            loop.close()
    else:
        uvicorn.Server(config).run()


if __name__ == "__main__":
    main()
