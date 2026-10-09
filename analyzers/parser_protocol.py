"""Owned helper packets preserve finished files if a later file exhausts a cap."""

import json


def completed_packets(output, files, maximum, performance=None, component=None):
    if len(output) > maximum:
        raise ValueError("Parser output budget exceeded")
    result = {}
    lines = output.splitlines()
    for index, line in enumerate(lines):
        try:
            packet = json.loads(line)
        except ValueError:
            # A killed helper may leave only its final packet incomplete.
            if index == len(lines) - 1 and not output.endswith(b"\n"):
                break
            raise ValueError("Parser packet is malformed") from None
        if packet.get("schema") != "projecttrace-parser-packet-v1" or packet.get("path") not in files:
            raise ValueError("Parser packet has invalid scope")
        path = packet["path"]
        if path in result:
            raise ValueError("Parser packet contains a duplicate path")
        result[path] = packet["result"]
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
