"""ProjectTrace-owned syntax helper. Input is data; imported source never runs."""

import json
import sys
import time
from pathlib import Path


def main():
    # -I removes user paths; explicitly add only this installed ProjectTrace root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.process_limits import self_limits
    self_limits(512 * 1024 * 1024, 25)
    from analyzers.engine import finding
    from analyzers.languages import LANGUAGES, _analyze_language
    from analyzers.parser_protocol import emit_packet

    payload = sys.stdin.buffer.read(21_000_001)
    if len(payload) > 21_000_000:
        raise ValueError("Native syntax input budget exceeded")
    files = json.loads(payload)
    if not isinstance(files, dict) or len(files) > 1000:
        raise ValueError("Native syntax file budget exceeded")
    metric_count, output_bytes = 0, 0
    for path, source in files.items():
        started, state = time.perf_counter(), "COMPLETED"
        try:
            if Path(path).suffix not in LANGUAGES or not isinstance(source, str) or len(source.encode()) > 512_000:
                raise ValueError("Unsupported native syntax input")
            parsed = _analyze_language(path, source, finding)
            metric_count += len(parsed[2])
            if metric_count > 10_000:
                raise ValueError("Native syntax metric budget exceeded")
            result = parsed
        except Exception as error:
            # Withhold diagnostic source/values; the parent marks coverage partial.
            result = {"error": "Native syntax parsing failed or exceeded its budget"}
            if isinstance(error, ValueError) and str(error) in {"Syntax node budget exceeded", "Syntax token budget exceeded"}:
                result.update(code="SYNTAX_NODE_BUDGET", budget="SYNTAX_NODES_OR_TOKENS", actual=40001, maximum=40000)
            state = "PARTIAL"
        output_bytes = emit_packet(path, result, time.perf_counter() - started, state,
                                   maximum=16_000_000, total=output_bytes)


if __name__ == "__main__":
    main()
