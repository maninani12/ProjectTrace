"""Time-clustered opaque storage IDs, independent of stable semantic identities."""
import secrets
import time
import uuid


def record_uid():
    """RFC 9562 §5.7 UUIDv7 with 74 CSPRNG bits; works on Python 3.12+.

    No hostname/MAC, source or tenant data enters the ID. Same-millisecond order
    is random; authorization never depends on secrecy or chronological order.
    Clock rollback affects locality, not collision resistance or data identity.
    """
    milliseconds, random = time.time_ns() // 1_000_000, secrets.randbits(74)
    return str(uuid.UUID(int=(milliseconds << 80) | (7 << 76) | ((random >> 62) << 64)
                         | (2 << 62) | (random & ((1 << 62) - 1))))
