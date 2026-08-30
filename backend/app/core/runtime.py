"""Runtime environment setup that must happen before anything else.

Import this first in every entrypoint (API server, worker, scripts).
"""

from __future__ import annotations

import asyncio
import sys


def configure_event_loop() -> None:
    """Select an asyncio event loop policy that psycopg can use.

    Windows defaults to ProactorEventLoop, which psycopg's async mode cannot
    drive -- it raises InterfaceError on the first connection attempt. Selector
    is required there. This is a no-op on other platforms, where the default
    loop is already compatible.

    Must run before any event loop is created, hence its own module imported at
    the top of each entrypoint.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
