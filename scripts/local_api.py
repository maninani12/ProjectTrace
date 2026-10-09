"""Operator-owned graceful API shutdown; imported source cannot signal it."""
import asyncio
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
STOP = ROOT / "data/local-api.stop"


async def main():
    STOP.unlink(missing_ok=True)
    # Bound draining disconnected HTTP clients. Lifespan still waits for the
    # fenced local worker's existing analysis budget; queued input stays durable.
    server = uvicorn.Server(uvicorn.Config("backend.main:app", host="127.0.0.1", port=8011, timeout_graceful_shutdown=30))

    async def watch():
        while not server.should_exit:
            if STOP.exists():
                server.should_exit = True
                break
            await asyncio.sleep(0.5)

    watcher = asyncio.create_task(watch())
    try:
        await server.serve()
    finally:
        watcher.cancel()
        STOP.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
