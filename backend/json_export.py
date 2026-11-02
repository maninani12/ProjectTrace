"""Incremental JSON exports, without collecting lazy map items or fragments.

Insertion order and the stdlib's default JSON spelling are retained. No sorting,
plaintext spool, global cache or new storage format is introduced. A stream owns
its iterators, never the caller's encrypted row owners. A failed sink may retain
a prefix; no successful receipt/publication is implied by writing that prefix.
"""
import io
import json
from contextlib import closing
from json.encoder import encode_basestring, encode_basestring_ascii

CHUNK_BYTES = 64 * 1024


def iter_text(value, *, default=None, ensure_ascii=True, allow_nan=True, separators=None):
    """Yield JSON without a document-wide collection of values or fragments.

    Scalars can be larger than a transport chunk, subject to the existing source
    row limits. This is not a new admission guard. As with json.dumps, callers
    must not concurrently mutate the document. ContextMap still authenticates
    every frame and verifies its HMAC index. Live state includes all active
    ancestor row payloads, traversal depth and the current escaped scalar token;
    caller-owned source data and default-callback allocations are additional.
    """
    item_separator, key_separator = separators if separators is not None else (", ", ": ")
    quote = encode_basestring_ascii if ensure_ascii else encode_basestring
    active, opened = set(), []

    def number(number):
        if isinstance(number, int):
            return int.__repr__(number)
        if number != number:
            text = "NaN"
        elif number == float("inf"):
            text = "Infinity"
        elif number == -float("inf"):
            text = "-Infinity"
        else:
            return float.__repr__(number)
        if not allow_nan:
            raise ValueError("Out of range float values are not JSON compliant: " + repr(number))
        return text

    def key_text(key):
        if isinstance(key, str):
            return quote(key)
        if key is True:
            return quote("true")
        if key is False:
            return quote("false")
        if key is None:
            return quote("null")
        if isinstance(key, (int, float)):
            return quote(number(key))
        raise TypeError("keys must be str, int, float, bool or None, not " + type(key).__name__)

    def walk(node):
        if isinstance(node, str):
            yield quote(node)
        elif node is None:
            yield "null"
        elif node is True:
            yield "true"
        elif node is False:
            yield "false"
        elif isinstance(node, (int, float)):
            yield number(node)
        else:
            identity = id(node)
            if identity in active:
                raise ValueError("Circular reference detected")
            active.add(identity)
            iterator = None
            try:
                if isinstance(node, (dict, list, tuple)):
                    mapping = isinstance(node, dict)
                    # Never list(items()), sorted(items()), or dict(node).
                    if mapping:
                        iterator = iter(getattr(node, "_json_items", node.items)())
                    else:
                        iterator = iter(getattr(node, "_json_iter", node.__iter__)())
                    opened.append(iterator)
                    yield "{" if mapping else "["
                    first = True
                    for entry in iterator:
                        if not first:
                            yield item_separator
                        first = False
                        if mapping:
                            key, child = entry
                            yield key_text(key)
                            yield key_separator
                        else:
                            child = entry
                        yield from walk(child)
                        del entry, child
                    yield "}" if mapping else "]"
                else:
                    if default is None:
                        raise TypeError("Object of type " + type(node).__name__ + " is not JSON serializable")
                    yield from walk(default(node))
            finally:
                if iterator is not None:
                    close = getattr(iterator, "close", None)
                    if close is not None:
                        close()
                    opened.pop()
                active.remove(identity)

    try:
        yield from walk(value)
    finally:
        # Explicitly unwind even when a consumer retains a failure traceback.
        # Only active ancestor iterators are retained, never a document-wide list.
        for iterator in reversed(opened):
            close = getattr(iterator, "close", None)
            if close is not None:
                close()
        opened.clear()
        active.clear()


def iter_bytes(value, *, checkpoint=None, **options):
    """UTF-8 chunks <=64 KiB. Close on abandonment; callback exceptions propagate."""
    separators = options.get("separators")
    ascii_only = options.get("ensure_ascii", True) and (separators is None or all(s.isascii() for s in separators))
    characters = CHUNK_BYTES if ascii_only else CHUNK_BYTES // 4
    with io.StringIO() as buffer, closing(iter_text(value, **options)) as parts:
        size = 0
        if checkpoint is not None:
            checkpoint()
        for ordinal, part in enumerate(parts):
            if checkpoint is not None and ordinal % 256 == 0:
                checkpoint()
            # Amortize UTF-8 encoding across tiny punctuation/scalar fragments.
            # The accumulator and the encoded chunk are each independently bounded.
            offset = 0
            while offset < len(part):
                take = min(characters - size, len(part) - offset)
                buffer.write(part[offset:offset + take])
                size += take
                offset += take
                if size == characters:
                    raw = buffer.getvalue().encode("utf-8")
                    buffer.seek(0)
                    buffer.truncate()
                    size = 0
                    yield raw
                    del raw
        if size:
            yield buffer.getvalue().encode("utf-8")
        if checkpoint is not None:
            checkpoint()


def write_json(value, sink, *, checkpoint=None, **options):
    """Write all bytes, handling short writes; return byte count only on success."""
    total = 0
    with closing(iter_bytes(value, checkpoint=checkpoint, **options)) as chunks:
        for chunk in chunks:
            remaining = memoryview(chunk)
            while remaining:
                if checkpoint is not None:
                    checkpoint()
                written = sink.write(remaining)
                if type(written) is not int or not 0 < written <= len(remaining):
                    raise OSError("JSON export sink did not accept a valid byte count.")
                total += written
                remaining = remaining[written:]
    return total


def _small_native(value, remaining):
    """Conservative, bounded fast path for ordinary small SQL JSON values."""
    remaining[0] -= 1
    if remaining[0] < 0:
        return False
    if type(value) in (str, int, float, bool, type(None)):
        return True
    if type(value) is dict:
        return all(type(key) in (str, int, float, bool, type(None)) and _small_native(child, remaining)
                   for key, child in value.items())
    if type(value) in (list, tuple):
        return all(_small_native(child, remaining) for child in value)
    return False


def dumps(value, *, default=None, ensure_ascii=True, allow_nan=True, separators=None):
    """SQLAlchemy-compatible str result. The final complete string is unavoidable.

    Stream to StringIO rather than collecting map items/fragments. Ordinary small
    native JSON keeps the stdlib accelerated path. No complete output is cached.
    """
    options = {"default": default, "ensure_ascii": ensure_ascii, "allow_nan": allow_nan, "separators": separators}
    if _small_native(value, [64]):
        return json.dumps(value, **options)
    with io.StringIO() as output, closing(iter_text(value, **options)) as parts:
        for part in parts:
            output.write(part)
        return output.getvalue()
