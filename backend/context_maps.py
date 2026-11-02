"""Ordered encrypted map views. Persistent working indexes contain HMACs only.

Storage/replay stream entries. Standard dict()/json.dumps() still materialize;
backend.json_export uses the authenticated, non-tracking export iterator.
"""
import hmac
import sqlite3
import weakref
from collections.abc import ItemsView, KeysView, ValuesView

from backend.checkpoint_pages import ReplayRows

# CPython's accelerated JSON encoder short-circuits physically empty dict
# subclasses. Keep one private base slot, and override the public mapping API.
# Both the Python and accelerated encoders use items() for a non-exact dict.
_BASE_SLOT = object()
_MISSING = object()


class Entries:
    def __init__(self, mapping):
        self.mapping = mapping

    def __len__(self):
        return len(self.mapping)

    def __iter__(self):
        for key, value in self.mapping.items():
            if type(key) is not str:
                raise ValueError("Generation context keys must be strings.")
            yield [key, value]


class MapItems(ItemsView):
    def __iter__(self):
        return self._mapping._iterate("items")


class MapValues(ValuesView):
    def __iter__(self):
        return self._mapping._iterate("values")


def entry_key(frame):
    kind, value = frame
    if kind == "E":
        if (not isinstance(value, list) or len(value) != 2 or value[0] != "inline"
                or not isinstance(value[1], list) or len(value[1]) != 2
                or not isinstance(value[1][0], list) or len(value[1][0]) != 2 or value[1][0][0] != "scalar"):
            raise ValueError("Generation map entry descriptor is invalid.")
        key = value[1][0][1]
    elif kind == "J" and isinstance(value, list) and len(value) == 2:
        key = value[0]
    else:
        raise ValueError("Generation map entry frame is invalid.")
    if type(key) is not str:
        raise ValueError("Generation map key is invalid.")
    return key


def index(connection):
    connection.execute("CREATE TABLE IF NOT EXISTS context_map_keys (collection INTEGER, tag BLOB, position INTEGER, PRIMARY KEY(collection,tag), UNIQUE(collection,position))")


def tag(secret, key):
    return hmac.digest(secret, key.encode("utf-8", "surrogatepass"), "sha256")


def admit_key(connection, secret, collection, position, key):
    try:
        connection.execute("INSERT INTO context_map_keys VALUES (?,?,?)", (collection, tag(secret, key), position))
    except sqlite3.IntegrityError as error:
        raise ValueError("Generation map contains duplicate keys or positions.") from error


class ContextMap(dict):
    _context_map = True

    def __init__(self, reader, descriptor):
        dict.__init__(self, {_BASE_SLOT: None})
        self.reader, self.descriptor = reader, descriptor
        self.rows = reader.memo[descriptor[1]][1]
        self.collection, self.count, self.version = descriptor[1], descriptor[2], 0
        self.live = weakref.WeakValueDictionary()

    @property
    def connection(self):
        self.rows._open()
        return self.rows.owner.rows.connection

    def __len__(self):
        self.rows._open()
        return self.count

    def _frame(self, position):
        return ReplayRows.__getitem__(self.rows, position)

    def _located(self, key):
        if type(key) is not str:
            hash(key)  # Match dict's TypeError for an unhashable lookup.
            raise KeyError(key)
        found = self.connection.execute("SELECT position FROM context_map_keys WHERE collection=? AND tag=?",
            (self.collection, tag(self.reader.map_secret, key))).fetchone()
        if found is None:
            raise KeyError(key)
        frame = self._frame(found[0])
        if entry_key(frame) != key:
            raise ValueError("Map key index does not match its encrypted entry.")
        return found[0], frame

    def _position(self, key):
        return self._located(key)[0]

    def __contains__(self, key):
        try:
            self._position(key)
            return True
        except KeyError:
            return False

    def __getitem__(self, key):
        position, frame = self._located(key)
        return self._value(position, key, frame)

    def _value(self, position, key, frame, *, track=True):
        # Retain the value-read open check formerly performed by ContextRows.
        # An owner can close after frame authentication, before value decoding.
        self.rows._open()
        if position in self.live:
            return self.live[position]
        pair = frame[1] if frame[0] == "J" else self.reader.restore(frame[1])
        value = pair[1]
        if track and isinstance(value, (dict, list)) and not isinstance(value, ContextMap):
            from backend.context_json import tracked
            root = []
            def changed():
                if self.live.get(position) is root[0]:
                    self._store(position, key, root[0])
            root.append(tracked(value, changed))
            self.live[position] = root[0]
            return root[0]
        return value

    def _store(self, position, key, value):
        frame = self.reader.mutable_frame([key, value])
        ReplayRows._replace(self.rows, position, frame)

    def __setitem__(self, key, value):
        if type(key) is not str:
            raise ValueError("Generation context keys must be strings.")
        try:
            position = self._position(key)
        except KeyError:
            frame = self.reader.mutable_frame([key, value])
            position = len(self.rows)
            self.rows.append_frame(frame)
            admit_key(self.connection, self.reader.map_secret, self.collection, position, key)
            self.count += 1
            self.version += 1
        else:
            self._store(position, key, value)
            self.live.pop(position, None)

    def __delitem__(self, key):
        position = self._position(key)
        self.connection.execute("DELETE FROM context_map_keys WHERE collection=? AND position=?", (self.collection, position))
        self.live.pop(position, None)
        self.count -= 1
        self.version += 1

    def _iterate(self, mode, reverse=False):
        version, seen = self.version, 0
        order = "DESC" if reverse else "ASC"
        cursor = self.connection.execute("SELECT position,tag FROM context_map_keys WHERE collection=? ORDER BY position " + order, (self.collection,))
        try:
            while True:
                self.rows._open()
                if version != self.version:
                    raise RuntimeError("Dictionary changed size during iteration")
                found = cursor.fetchone()
                if found is None:
                    break
                position, expected = found
                frame = self._frame(position)
                key = entry_key(frame)
                if tag(self.reader.map_secret, key) != expected:
                    raise ValueError("Map key index does not match its encrypted entry.")
                result = key if mode == "keys" else self._value(position, key, frame, track=mode != "json")
                # Reuse is confined to this step. Do not retain a decoded frame
                # across yield or make a cache that can outlive a mutation.
                del frame
                if mode in ("items", "json"):
                    result = (key, result)
                seen += 1
                try:
                    yield result
                finally:
                    del result
            if version != self.version:
                raise RuntimeError("Dictionary changed size during iteration")
            if seen != self.count:
                raise ValueError("Map index is incomplete.")
        finally:
            if not self.rows.closed:
                cursor.close()

    def __iter__(self):
        return self._iterate("keys")

    def __reversed__(self):
        return self._iterate("keys", reverse=True)

    def keys(self):
        return KeysView(self)

    def items(self):
        return MapItems(self)

    def _json_items(self):
        # Read-only serialization must not create cyclic write-through wrappers
        # for every visited value. It still uses exactly the same frame/HMAC,
        # mutation-version, completeness and mid-read owner-open checks.
        return self._iterate("json")

    def values(self):
        return MapValues(self)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]

    def pop(self, key, default=_MISSING):
        try:
            value = self[key]
        except KeyError:
            if default is _MISSING:
                raise
            return default
        del self[key]
        return value

    def popitem(self):
        cursor = reversed(self)
        try:
            key = next(cursor)
        except StopIteration:
            raise KeyError("popitem(): dictionary is empty") from None
        finally:
            cursor.close()
        return key, self.pop(key)

    def clear(self):
        self.connection.execute("DELETE FROM context_map_keys WHERE collection=?", (self.collection,))
        if self.count:
            self.version += 1
        self.count = 0
        self.live.clear()

    def update(self, other=(), **kwargs):
        pairs = ((key, other[key]) for key in other.keys()) if hasattr(other, "keys") else other
        for key, value in pairs:
            self[key] = value
        for key, value in kwargs.items():
            self[key] = value

    def copy(self):
        return dict(self.items())

    def __copy__(self):
        return self.copy()

    def __deepcopy__(self, memo):
        from copy import deepcopy
        result = {}
        memo[id(self)] = result
        for key, value in self.items():
            result[key] = deepcopy(value, memo)
        return result

    def __eq__(self, other):
        if not isinstance(other, dict):
            return NotImplemented
        return len(self) == len(other) and all(key in other and value == other[key] for key, value in self.items())

    def __ne__(self, other):
        result = self.__eq__(other)
        return NotImplemented if result is NotImplemented else not result

    def __ior__(self, other):
        self.update(other)
        return self

    def __or__(self, other):
        if not isinstance(other, dict):
            return NotImplemented
        result = self.copy()
        result.update(other)
        return result

    def __ror__(self, other):
        if not isinstance(other, dict):
            return NotImplemented
        result = dict(other)
        result.update(self.items())
        return result

    def __repr__(self):
        return f"ContextMap({self.count} ordered encrypted entries)"
