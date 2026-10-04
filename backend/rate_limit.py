"""Separate local/distributed admission policies; Redis failure is fail-closed in production."""

import hashlib
import os
import time
from collections import defaultdict, deque

windows = defaultdict(deque)
LIMITS = {"login": 15, "imports": 10, "analysis": 10, "ask": 60, "webhook": 120, "provider": 20, "general": 240}
LUA = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], 60) end
return count
"""


def bucket(path, method):
    if method != "POST":
        return "general"
    if path in {"/api/auth/login", "/api/auth/demo", "/api/auth/register"}:
        return "login"
    if path in {"/api/import", "/api/archive/import"}:
        return "imports"
    if path.endswith("/analyze") or "/jobs/" in path:
        return "analysis"
    if path == "/api/ask":
        return "ask"
    if path == "/api/github/webhook":
        return "webhook"
    if path.startswith("/api/connections") or path.endswith("/advisories"):
        return "provider"
    return "general"


def allow(identity, policy, *, distributed=False):
    limit = LIMITS[policy]
    if distributed:
        import redis

        client = redis.Redis.from_url(os.environ["REDIS_URL"], socket_timeout=2, socket_connect_timeout=2)
        key = hashlib.sha256((identity + ":" + policy).encode()).hexdigest()
        return int(client.eval(LUA, 1, "projecttrace:rate:" + key)) <= limit
    key = (identity, policy)
    window, current = windows[key], time.monotonic()
    while window and current - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        return False
    window.append(current)
    # Keep local anonymous clients from creating an unbounded map.
    if len(windows) > 10000:
        for old_key in list(windows)[:1000]:
            if not windows[old_key] or current - windows[old_key][-1] > 60:
                del windows[old_key]
    return True
