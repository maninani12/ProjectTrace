"""Owned helper packets preserve finished files if a later file exhausts a cap."""

import json
import math

from analyzers.sandbox import decode_packet
from analyzers.sanitization import metadata


def completed_packets(output, files, maximum, performance=None, component=None):
    if len(output) > maximum:
        raise ValueError("Parser output budget exceeded")
    result = {}
    lines = output.splitlines()
    for index, line in enumerate(lines):
        try:
            packet = decode_packet(line)
        except ValueError:
            # A killed helper may leave only its final packet incomplete.
            if index == len(lines) - 1 and not output.endswith(b"\n"):
                break
            raise ValueError("Parser packet is malformed") from None
        if not isinstance(packet, dict) or packet.get("schema") != "projecttrace-parser-packet-v1" or packet.get("path") not in files:
            raise ValueError("Parser packet has invalid scope")
        if (set(packet) != {"schema", "path", "result", "seconds", "state"}
                or type(packet["seconds"]) not in {int, float} or not math.isfinite(packet["seconds"])
                or not 0 <= packet["seconds"] <= 150 or packet["state"] not in {"COMPLETED", "PARTIAL", "FAILED"}):
            raise ValueError("Parser packet has invalid schema")
        path = packet["path"]
        if path in result:
            raise ValueError("Parser packet contains a duplicate path")
        result[path] = metadata(packet["result"])
        if performance:
            performance.record(component, packet["seconds"], path, state=packet["state"])
    return result


def emit_packet(path, result, seconds, state, *, maximum, total):
    import sys
    packet = json.dumps({"schema": "projecttrace-parser-packet-v1", "path": path, "result": result,
                         "seconds": round(seconds, 6), "state": state}, ensure_ascii=True).encode() + b"\n"
    total += len(packet)
    if total > maximum:
        raise ValueError("Parser output budget exceeded")
    sys.stdout.buffer.write(packet)
    sys.stdout.buffer.flush()
    return total
