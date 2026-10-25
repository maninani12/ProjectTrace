"""Trusted, bounded final privacy guard. No regex or repository-defined grammar.

This fixed-format scanner is deliberately independent of parser helpers. It
does not identify all possible secrets; it enforces ProjectTrace's supported
credential forms even if a compromised helper omits its own redaction.
"""

import math

MAX_TEXT = 1_000_000
PRIVATE_LABELS = ("PRIVATE KEY-----", "RSA PRIVATE KEY-----", "EC PRIVATE KEY-----", "OPENSSH PRIVATE KEY-----")
SENSITIVE_KEYS = {"password", "passwd", "token", "access_token", "refresh_token", "secret", "secret_key",
                  "client_secret", "api_key", "apikey", "authorization", "cookie", "credentials",
                  "database_url", "private_key"}


def _private(text):
    chunks, offset = [], 0
    while True:
        start = text.find("-----BEGIN ", offset)
        if start < 0:
            chunks.append(text[offset:])
            break
        if not any(text.startswith(label, start + 11) for label in PRIVATE_LABELS):
            chunks.append(text[offset:start + 11])
            offset = start + 11
            continue
        end = start + 11
        while True:
            end = text.find("-----END ", end)
            if end < 0:
                end = len(text)
                break
            label = next((label for label in PRIVATE_LABELS if text.startswith(label, end + 9)), None)
            if label:
                end += 9 + len(label)
                break
            end += 9
        chunks.extend((text[offset:start], "[REDACTED PRIVATE KEY]"))
        offset = end
    return "".join(chunks)


def _urls(text):
    out, offset, search = [], 0, 0
    while True:
        delimiter = text.find("://", search)
        if delimiter < 0:
            break
        search = delimiter + 3
        start = delimiter
        while start and (text[start - 1].isalnum() or text[start - 1] in "_+"):
            start -= 1
        scheme = text[start:delimiter].lower().split("+", 1)
        if scheme[0] not in {"postgres", "postgresql", "mysql", "mongodb"}:
            continue
        if len(scheme) == 2 and (not scheme[1] or not all(c.isalnum() or c == "_" for c in scheme[1])):
            continue
        user = search
        while user < len(text) and not text[user].isspace() and text[user] not in "/:":
            user += 1
        if user == search or user == len(text) or text[user] != ":":
            continue
        end = user + 1
        while end < len(text) and not text[end].isspace() and text[end] not in "/@":
            end += 1
        if end > user + 1 and end < len(text) and text[end] == "@":
            out.extend((text[offset:user + 1], "[REDACTED]"))
            offset, search = end, end + 1
    out.append(text[offset:])
    return "".join(out)


def _assignments(text):
    out = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        ending = line[len(body):]
        equal = body.find("=")
        name = body[:equal].rstrip() if equal >= 0 else ""
        upper = (name and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ_" for c in name)
                 and name.endswith(("PASSWORD", "TOKEN", "SECRET", "API_KEY")))
        redact = bool(upper and body[equal + 1:].strip())
        if not redact:
            start = body.lstrip()
            stop = 0
            while stop < len(start) and (start[stop].isalnum() or start[stop] in "_-"):
                stop += 1
            label, rest = start[:stop].lower(), start[stop:].lstrip()
            if label and any(marker in label for marker in ("password", "token", "secret", "api_key", "api-key", "apikey")) and rest[:1] in {":", "="}:
                value = rest[1:].lstrip()
                stop = 0
                while stop < len(value) and value[stop] in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_+/=-":
                    stop += 1
                tail = value[stop:].lstrip()
                redact = stop >= 12 and (not tail or tail.startswith("#"))
        out.append(("[REDACTED ENVIRONMENT SECRET]" if redact else body) + ending)
    return "".join(out)


def redact(text):
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise ValueError("Sanitization text budget or type invalid")
    text = _assignments(_urls(_private(text)))
    chunks, last, i = [], 0, 0
    keywords = ("password", "api_key", "api-key", "apikey", "secret_key", "secret", "token")
    while i < len(text):
        if text[i] not in "gGaApPsStT":
            i += 1
            continue
        end = i
        prefix = text[i:i + 4].lower()
        if prefix in {"ghp_", "gho_", "ghu_", "ghs_", "ghr_"}:
            end = i + 4
            while end < len(text) and text[end] in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_":
                end += 1
            if end - i < 24:
                end = i
        elif prefix == "akia" and len(text) >= i + 20 and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789" for c in text[i + 4:i + 20]):
            end = i + 20
        else:
            word = next((word for word in keywords if text[i:i + len(word)].lower() == word), None)
            if word:
                j = i + len(word)
                while j < len(text) and text[j].isspace():
                    j += 1
                if j < len(text) and text[j] in ":=":
                    j += 1
                    while j < len(text) and text[j].isspace():
                        j += 1
                    if j < len(text) and text[j] in "\"'":
                        start = j + 1
                        j = start
                        while j < len(text) and text[j] not in "\"'\n":
                            j += 1
                        if j - start >= 12 and j < len(text) and text[j] in "\"'":
                            end = j + 1
        if end > i:
            chunks.extend((text[last:i], "[REDACTED SECRET]"))
            last, i = end, end
        else:
            i += 1
    chunks.append(text[last:])
    return "".join(chunks)


def metadata(value, *, maximum_nodes=1_000_000):
    """Fail closed for cycles/depth, invalid scalars and colliding sanitized keys."""
    nodes = 0
    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        if depth > 60 or nodes > maximum_nodes:
            raise ValueError("Sanitization structure budget exceeded")
        if item is None or type(item) in {bool, int}:
            return item
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError("Non-finite metadata is invalid")
            return item
        if isinstance(item, str):
            return redact(item)
        if isinstance(item, (list, tuple)):
            children = [visit(child, depth + 1) for child in item]
            return tuple(children) if isinstance(item, tuple) else children
        if isinstance(item, dict):
            output = {}
            for key, child in item.items():
                if type(key) not in {str, int}:
                    raise ValueError("Metadata key type invalid")
                name = redact(str(key))
                if name in output:
                    raise ValueError("Sanitized metadata key collision")
                lowered = name.lower().replace("-", "_")
                sensitive = lowered in SENSITIVE_KEYS or lowered.endswith(("_password", "_access_token", "_client_secret"))
                output[name] = "[REDACTED]" if sensitive and child is not None else visit(child, depth + 1)
            return output
        raise ValueError("Metadata type invalid")
    return visit(value, 0)
