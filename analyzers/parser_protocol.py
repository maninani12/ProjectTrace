"""Owned helper packets preserve finished files if a later file exhausts a cap."""

import json
import math

from analyzers.sandbox import decode_packet
from analyzers.sanitization import metadata

NATIVE_ARTIFACT_SCHEMA = "projecttrace-native-artifact-v1"
NATIVE_FIELDS = (("findings", 0), ("signals", 1), ("warnings", 2), ("assets", 3), ("quality_metrics", 4))


def native_artifact(path, result):
    """Transmit the completed cache artifact once, without repeated payloads."""
    if not isinstance(result, list) or len(result) != 9 or set(result[6]) != {path}:
        raise ValueError("Native artifact result scope is invalid")
    artifact = result[6][path]
    if any(artifact.get(key) != result[index] for key, index in NATIVE_FIELDS):
        raise ValueError("Native artifact observations are inconsistent")
    return {"schema": NATIVE_ARTIFACT_SCHEMA, "artifact": artifact, "failures": result[5],
            "reused": result[7], "performance": result[8]}


def expand_native_artifact(path, result):
    """Restore the existing result before the independent privacy/schema gate.

    Legacy list results remain readable. metadata() subsequently visits both
    projections, enforcing the original logical node/depth budgets and making
    independent mutable copies for observations and durable cache input.
    """
    if not isinstance(result, dict):
        return result
    if (set(result) != {"schema", "artifact", "failures", "reused", "performance"}
            or result.get("schema") != NATIVE_ARTIFACT_SCHEMA or not isinstance(result["artifact"], dict)
            or any(key not in result["artifact"] for key, _ in NATIVE_FIELDS)):
        raise ValueError("Native artifact envelope is invalid")
    artifact = result["artifact"]
    return [*[artifact[key] for key, _ in NATIVE_FIELDS], result["failures"], {path: artifact},
            result["reused"], result["performance"]]


def completed_packets(output, files, maximum, performance=None, component=None, *, expand=None):
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
        value = expand(path, packet["result"]) if expand else packet["result"]
        result[path] = metadata(value)
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
