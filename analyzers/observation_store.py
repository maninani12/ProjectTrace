"""Attempt-private encrypted spill rows; only typed observations cross this boundary.

Rows are immutable snapshots, not mutable list elements. No source path controls
storage names and no key or storage handle is passed to a parser subprocess.
This bounds resident observation payloads, not every global analyzer index.
"""

import json
import os
import sqlite3
import uuid
import weakref
import zlib
from collections.abc import Sequence
from itertools import zip_longest

from cryptography.fernet import Fernet


_FAST_JSON_SERIALIZATION_BYTES = 4_000_000


def _json_size_upper_bound(value, maximum, depth=0):
    """Conservative ASCII-JSON byte bound; return maximum + 1 when not safely small."""
    if maximum < 0 or depth > 100:
        return maximum + 1
    kind = type(value)
    if kind is str:
        size = 12 * len(value) + 2  # ensure_ascii escapes astral codepoints as surrogate pairs
        return size if size <= maximum else maximum + 1
    if value is None:
        return 4
    if kind is bool:
        return 4 if value is False else 5
    if kind is int:
        try:
            size = len(str(value))
        except ValueError:
            return maximum + 1
        return size if size <= maximum else maximum + 1
    if kind is float:
        size = len(json.dumps(value, ensure_ascii=True, separators=(",", ":")))
        return size if size <= maximum else maximum + 1
    if kind in (list, tuple):
        size = 2 + max(0, len(value) - 1)
        if size > maximum:
            return maximum + 1
        for item in value:
            size += _json_size_upper_bound(item, maximum - size, depth + 1)
            if size > maximum:
                return maximum + 1
        return size
    if kind is dict:
        size = 2 + max(0, len(value) - 1)
        if size > maximum:
            return maximum + 1
        for key, item in value.items():
            # Fast path is for the internal string-keyed JSON schema. Preserve
            # JSONEncoder compatibility for other mappings with the fallback.
            if type(key) is not str:
                return maximum + 1
            size += _json_size_upper_bound(key, maximum - size, depth + 1) + 1
            if size > maximum:
                return maximum + 1
            size += _json_size_upper_bound(item, maximum - size, depth + 1)
            if size > maximum:
                return maximum + 1
        return size
    return maximum + 1


def _bounded_json_bytes(value, maximum, *, rows=0, collection="OBSERVATIONS"):
    """Use the C-backed encoder only when a conservative bound guarantees a small row."""
    fast_limit = min(maximum, _FAST_JSON_SERIALIZATION_BYTES)
    if _json_size_upper_bound(value, fast_limit) <= fast_limit:
        raw = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        # Defensive equality check: the upper bound should make this impossible,
        # but the row budget is authoritative even if the estimator changes.
        if len(raw) > maximum:
            raise ObservationBudgetExceeded(
                "Typed observation exceeds its spill row budget.", budget="ROW_BYTES",
                maximum=maximum, actual=len(raw), rows=rows, collection=collection,
            )
        return raw

    # Larger/unknown structures keep the incremental encoder: this guarantees
    # rejection at row_bytes instead of materializing an arbitrarily large JSON string.
    raw = bytearray()
    encoder = json.JSONEncoder(ensure_ascii=True, separators=(",", ":"))
    for part in encoder.iterencode(value):
        encoded = part.encode()
        if len(raw) + len(encoded) > maximum:
            raise ObservationBudgetExceeded(
                "Typed observation exceeds its spill row budget.", budget="ROW_BYTES",
                maximum=maximum, actual=len(raw) + len(encoded), rows=rows, collection=collection,
            )
        raw.extend(encoded)
    return bytes(raw)


class ObservationBudgetExceeded(ValueError):
    def __init__(self, message, *, budget=None, maximum=None, actual=None, rows=None, collection=None):
        super().__init__(message)
        self.budget, self.maximum, self.actual, self.rows, self.collection = budget, maximum, actual, rows, collection


class EncryptedRows(list):
    # A list subclass is intentional: the existing streaming JSON encoders can
    # iterate rows without materializing them. All ordinary mutation is rejected.
    def __init__(self, scope, *, maximum_bytes=None, row_bytes=32_000_000):
        super().__init__()
        maximum_bytes = int(os.getenv("ANALYSIS_OBSERVATION_SPILL_BYTES", "256000000")) if maximum_bytes is None else maximum_bytes
        if not 1 <= row_bytes <= maximum_bytes <= 2_000_000_000:
            raise ValueError("Observation spill budgets are invalid.")
        self.label = "OBSERVATIONS"
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
        raw = _bounded_json_bytes(envelope, self.row_bytes, rows=self._count, collection=self.label)
        # Compress only our own bounded JSON envelope, before authentication.
        # Token windows repeat JSON keys/values heavily; retaining their verbose
        # representation exhausted the disk budget on the pinned workload.
        # This changes no observation, ordering, row or ciphertext budget.
        return self.key.encrypt(b"PTZ1" + zlib.compress(raw, level=1))

    def append(self, value):
        ciphertext = self._encrypted(self._count, value)
        if self.bytes + len(ciphertext) > self.maximum_bytes:
            raise ObservationBudgetExceeded("Typed observations exceed the attempt spill byte budget.", budget="COLLECTION_BYTES",
                maximum=self.maximum_bytes, actual=self.bytes + len(ciphertext), rows=self._count, collection=self.label)
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
            raise ObservationBudgetExceeded("Typed observations exceed the attempt spill byte budget.", budget="COLLECTION_BYTES",
                maximum=self.maximum_bytes, actual=size, rows=self._count, collection=self.label)
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
        packed = self.key.decrypt(row[0])
        if not packed.startswith(b"PTZ1"):
            raise ValueError("Observation spill encoding is invalid.")
        decoder = zlib.decompressobj()
        raw = decoder.decompress(packed[4:], self.row_bytes + 1)
        if (len(raw) > self.row_bytes or decoder.unconsumed_tail or not decoder.eof or decoder.unused_data):
            raise ValueError("Observation spill decoded row exceeds its budget or encoding.")
        value = json.loads(raw)
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
        return self.select_positions(i for i, value in enumerate(self) if predicate(value))

    def select_positions(self, positions):
        """Return a lazy view over known row offsets; never copy encrypted payloads."""
        selected = list(positions)
        if any(type(position) is not int or not 0 <= position < self._count for position in selected):
            raise IndexError("Selected observation row position is out of range.")
        return SelectedRows(self, selected)

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
        self.rows.label = "FINDING_WORKING_STATE"
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


class SignalRows(EncryptedRows):
    """Private exact/type indexes avoid decrypting every signal for each claim.

    Values and import roots are HMAC tags, not plaintext source-derived values.
    Verifiers still apply their original predicates to the selected typed rows.
    """
    VALUE_TYPES = {"technology", "database", "import", "auth", "auth_hint", "route", "authorization",
                   "infrastructure", "testing", "ci", "security_control", "configuration"}

    def __init__(self, scope):
        import secrets
        super().__init__(scope)
        self.index_key = secrets.token_bytes(32)
        self.connection.execute("CREATE TABLE signal_lookup (ordinal INTEGER PRIMARY KEY, kind BLOB, exact BLOB, root BLOB)")
        self.connection.execute("CREATE INDEX signal_exact ON signal_lookup(kind,exact,ordinal)")
        self.connection.execute("CREATE INDEX signal_root ON signal_lookup(kind,root,ordinal)")

    def _tag(self, value):
        import hashlib
        import hmac
        return hmac.digest(self.index_key, value.encode(), hashlib.sha256)

    def append(self, value):
        if not isinstance(value, dict) or not isinstance(value.get("type"), str):
            raise ValueError("Typed signal has no valid type.")
        kind, material = value["type"], value.get("value")
        if kind in self.VALUE_TYPES and not isinstance(material, str):
            raise ValueError("Verifier signal has no valid typed value.")
        exact = self._tag(material.lower()) if isinstance(material, str) else None
        root = self._tag(material.split(".", 1)[0].lower()) if kind == "import" else None
        position = len(self)
        super().append(value)
        self.connection.execute("INSERT INTO signal_lookup VALUES (?,?,?,?)", (position, self._tag(kind), exact, root))

    def _selected(self, query, parameters):
        # Fetch ordinals lazily. The returned row keeps its original identity,
        # provenance, context fields and order; nothing is synthesized/truncated.
        cursor = self.connection.execute(query, parameters)
        try:
            for position, in cursor:
                yield self[position]
        finally:
            cursor.close()

    def types(self, kinds):
        if not kinds:
            return iter(())
        tags = [self._tag(kind) for kind in sorted(kinds)]
        return self._selected("SELECT ordinal FROM signal_lookup WHERE kind IN (" + ",".join("?" for _ in tags) + ") ORDER BY ordinal", tags)

    def verifier_inputs(self, kinds, expected, aliases):
        if not kinds:
            return iter(())
        tags = [self._tag(kind) for kind in sorted(kinds)]
        condition = "(kind IN (" + ",".join("?" for _ in tags) + ") AND exact=?)"
        parameters = [*tags, self._tag(expected)]
        if "import" in kinds:
            roots = [self._tag(alias) for alias in sorted(aliases)]
            condition += " OR (kind=? AND root IN (" + ",".join("?" for _ in roots) + "))"
            parameters.extend([self._tag("import"), *roots])
        return self._selected("SELECT ordinal FROM signal_lookup WHERE " + condition + " ORDER BY ordinal", parameters)
