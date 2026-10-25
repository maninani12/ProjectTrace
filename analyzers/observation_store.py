"""Attempt-private encrypted spill rows; only typed observations cross this boundary.

Rows are immutable snapshots, not mutable list elements. No source path controls
storage names and no key or storage handle is passed to a parser subprocess.
This bounds resident observation payloads, not every global analyzer index.
"""

import json
import sqlite3
import uuid
import weakref
from collections.abc import Sequence
from itertools import zip_longest

from cryptography.fernet import Fernet


class ObservationBudgetExceeded(ValueError):
    pass


class EncryptedRows(list):
    # A list subclass is intentional: the existing streaming JSON encoders can
    # iterate rows without materializing them. All ordinary mutation is rejected.
    def __init__(self, scope, *, maximum_bytes=256_000_000, row_bytes=32_000_000):
        super().__init__()
        if not 1 <= row_bytes <= maximum_bytes <= 2_000_000_000:
            raise ValueError("Observation spill budgets are invalid.")
        self.scope = tuple(scope)
        self.identity = str(uuid.uuid4())
        self.key = Fernet(Fernet.generate_key())
        self.maximum_bytes, self.row_bytes = maximum_bytes, row_bytes
        self._count = self.bytes = 0
        self.closed = False
        # SQLite's unnamed temporary database uses an already-unlinked file on
        # Linux. Kernel FD cleanup reclaims it even after SIGKILL; no ephemeral
        # key or durable ciphertext orphan is needed by a later retry.
        self.connection = sqlite3.connect("", check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=OFF")
        self.connection.execute("PRAGMA cache_size=-1024")
        self.connection.execute("PRAGMA mmap_size=0")
        self.connection.execute("CREATE TABLE rows (ordinal INTEGER PRIMARY KEY, ciphertext BLOB NOT NULL)")
        self.cleanup = weakref.finalize(self, self.connection.close)

    def close(self):
        if not self.closed:
            self.closed = True
            self.cleanup()

    def _open(self):
        if self.closed:
            raise ValueError("Observation spill is closed.")

    def __len__(self):
        return self._count

    def _encrypted(self, position, value):
        self._open()
        envelope = [self.identity, self.scope, position, value]
        raw = bytearray()
        for part in json.JSONEncoder(ensure_ascii=True, separators=(",", ":")).iterencode(envelope):
            encoded = part.encode()
            if len(raw) + len(encoded) > self.row_bytes:
                raise ObservationBudgetExceeded("Typed observation exceeds its spill row budget.")
            raw.extend(encoded)
        return self.key.encrypt(bytes(raw))

    def append(self, value):
        ciphertext = self._encrypted(self._count, value)
        if self.bytes + len(ciphertext) > self.maximum_bytes:
            raise ObservationBudgetExceeded("Typed observations exceed the attempt spill byte budget.")
        self.connection.execute("INSERT INTO rows VALUES (?, ?)", (self._count, ciphertext))
        self._count += 1
        self.bytes += len(ciphertext)

    def _replace(self, position, value):
        # Only the explicit mutable working-map owner may replace a row.
        old = self.connection.execute("SELECT length(ciphertext) FROM rows WHERE ordinal=?", (position,)).fetchone()
        if old is None:
            raise KeyError(position)
        ciphertext = self._encrypted(position, value)
        size = self.bytes - old[0] + len(ciphertext)
        if size > self.maximum_bytes:
            raise ObservationBudgetExceeded("Typed observations exceed the attempt spill byte budget.")
        self.connection.execute("UPDATE rows SET ciphertext=? WHERE ordinal=?", (ciphertext, position))
        self.bytes = size

    def extend(self, values):
        for value in values:
            self.append(value)

    def __getitem__(self, position):
        self._open()
        if isinstance(position, slice):
            return [self[i] for i in range(*position.indices(self._count))]
        if not isinstance(position, int):
            raise TypeError("Observation position must be an integer.")
        if position < 0:
            position += self._count
        if not 0 <= position < self._count:
            raise IndexError(position)
        row = self.connection.execute("SELECT ciphertext FROM rows WHERE ordinal=?", (position,)).fetchone()
        if row is None:
            raise ValueError("Observation spill row is missing.")
        value = json.loads(self.key.decrypt(row[0]))
        if value[:3] != [self.identity, list(self.scope), position] or len(value) != 4:
            raise ValueError("Observation spill scope or ordinal is invalid.")
        return value[3]

    def __iter__(self):
        for position in range(self._count):
            yield self[position]

    def __eq__(self, other):
        if not isinstance(other, (list, tuple)):
            return NotImplemented
        missing = object()
        return all(a == b for a, b in zip_longest(self, other, fillvalue=missing))

    def __ne__(self, other):
        equal = self.__eq__(other)
        return NotImplemented if equal is NotImplemented else not equal

    def __contains__(self, value):
        return any(row == value for row in self)

    def __reversed__(self):
        for position in range(self._count - 1, -1, -1):
            yield self[position]

    def select(self, predicate):
        return SelectedRows(self, [i for i, value in enumerate(self) if predicate(value)])

    def _immutable(self, *args, **kwargs):
        raise TypeError("Observation rows are immutable snapshots; append new rows instead.")

    __setitem__ = __delitem__ = insert = pop = remove = clear = reverse = sort = _immutable
    __iadd__ = __imul__ = __add__ = __radd__ = __mul__ = __rmul__ = _immutable

    def copy(self):
        return list(self)

    def count(self, value):
        return sum(row == value for row in self)

    def index(self, value, start=0, stop=None):
        for position in range(start, len(self) if stop is None else min(stop, len(self))):
            if self[position] == value:
                return position
        raise ValueError("Observation value is not present.")


class SelectedRows(Sequence):
    """Only integer offsets are retained; duplication can still use random access."""
    def __init__(self, owner, positions):
        self.owner, self.positions = owner, positions

    def __len__(self):
        return len(self.positions)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self.owner[p] for p in self.positions[index]]
        return self.owner[self.positions[index]]


class EncryptedMapping:
    """Attempt-local mutable index; full keys/values remain encrypted on disk."""
    def __init__(self, scope):
        import secrets
        self.rows = EncryptedRows(scope)
        self.secret = secrets.token_bytes(32)
        self.rows.connection.execute("CREATE TABLE keys (key BLOB PRIMARY KEY, ordinal INTEGER UNIQUE NOT NULL)")

    def _key(self, identity):
        import hashlib
        import hmac
        if not isinstance(identity, str) or len(identity) > 1000:
            raise ValueError("Working-state identity is invalid.")
        return hmac.digest(self.secret, identity.encode(), hashlib.sha256)

    def __setitem__(self, identity, data):
        key = self._key(identity)
        row = self.rows.connection.execute("SELECT ordinal FROM keys WHERE key=?", (key,)).fetchone()
        value = {"id": identity, "data": data}
        if row is None:
            ordinal = len(self.rows)
            self.rows.append(value)
            self.rows.connection.execute("INSERT INTO keys VALUES (?, ?)", (key, ordinal))
        else:
            self.rows._replace(row[0], value)

    def __getitem__(self, identity):
        row = self.rows.connection.execute("SELECT ordinal FROM keys WHERE key=?", (self._key(identity),)).fetchone()
        if row is None:
            raise KeyError(identity)
        value = self.rows[row[0]]
        if value["id"] != identity:
            raise ValueError("Working-state key does not match its encrypted row.")
        return value["data"]

    def __contains__(self, identity):
        return self.rows.connection.execute("SELECT 1 FROM keys WHERE key=?", (self._key(identity),)).fetchone() is not None

    def __len__(self):
        return len(self.rows)

    def snapshots(self):
        return self.rows

    def close(self):
        self.rows.close()
