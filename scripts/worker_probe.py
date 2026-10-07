"""Bounded local-worker readiness through the configured private broker."""
import socket

from workers.tasks import celery

if __name__ == "__main__":
    destination = "celery@" + socket.gethostname()
    result = celery.control.inspect(destination=[destination], timeout=2).ping()
    raise SystemExit(0 if result and result.get(destination, {}).get("ok") == "pong" else 1)
