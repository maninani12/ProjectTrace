"""Qualification-only operation boundaries; never records arguments or source.

Wrappers preserve the returned object and exceptions. Native parsing is left
unprofiled; its existing timing/packet counters remain authoritative. RSS and
cgroup charge are distinct. A flushed START without END localizes a killed
operation, but lifetime HWM counters are not per-operation peaks.
"""
import inspect
import json
import time
from contextlib import ExitStack, contextmanager
from functools import wraps

from scripts.scale_linux_resources import memory


@contextmanager
def operation_probe(stage, path, started, *, sample=memory, scenario=None):
    from analyzers import engine, lexical, lexical_worker
    from analyzers.code_quality import core
    from backend import analysis_checkpoints, publication_units
    from backend.generations import Generation

    targets = [
        (engine, "verify_claim", "CLAIM_VERIFIER"),
        (lexical, "storage_claims", "STORAGE_CLAIMS"),
        (lexical_worker, "storage_claims", "STORAGE_CLAIMS"),
        (engine, "link_local_declarations", "INFRASTRUCTURE_LINKS"),
        (engine, "quality_build", "QUALITY_BUILD"),
        (core, "build", "QUALITY_BUILD"),
        (core, "classify", "QUALITY_INVENTORY"),
        (core, "detect", "QUALITY_DUPLICATION"),
        (engine, "annotate_finding_identity", "FINAL_IDENTITY"),
        (engine, "implementation_claims", "IMPLEMENTATION_CLAIMS"),
        (analysis_checkpoints, "save", "GLOBAL_CHECKPOINT"),
        (publication_units, "prepare", "PUBLICATION_PREPARATION"),
        (Generation, "validate", "GENERATION_VALIDATE"),
        (Generation, "promote", "GENERATION_PROMOTE"),
    ]
    sequence, parents = [0], []
    ignored = {"INITIALIZING", "ARCHIVE_TO_ENCRYPTED_REPLAY", "CAPTURING", "VALIDATING", "PARSING", "ANALYZING"}
    phases = {"METRIC_PROJECTION", "METRIC_OWNER_INDEX", "PRODUCTION_METRIC_SELECTION", "QUALITY_SYMBOLS", "QUALITY_RULES"}
    with path.open("x", encoding="utf-8") as stream, ExitStack() as restore:
        def emit(event, operation, identity, parent):
            row = {"schema": "scale-operation-memory-v1", "event": event, "operation": operation,
                   "call": identity, "parent": parent, "stage": stage[0],
                   "scenario": scenario[0] if scenario else None,
                   "elapsed_seconds": round(time.monotonic() - started, 6), "memory": sample()}
            stream.write(json.dumps(row) + "\n")
            stream.flush()

        def instrument(original, operation):
            @wraps(original)
            def measured(*args, **kwargs):
                if stage[0] in ignored:
                    return original(*args, **kwargs)
                sequence[0] += 1
                identity, parent = sequence[0], parents[-1] if parents else None
                emit("START", operation, identity, parent)
                depth = len(parents)
                parents.append(identity)
                active = {}

                def point(name, event):
                    if name not in phases or event not in {"START", "END"}:
                        raise ValueError("Invalid owned operation phase")
                    if event == "START":
                        sequence[0] += 1
                        active[name] = (sequence[0], parents[-1])
                        emit(event, name, *active[name])
                        parents.append(active[name][0])
                    else:
                        current = active.pop(name)
                        if parents[-1] != current[0]:
                            raise ValueError("Invalid owned operation nesting")
                        emit(event, name, *current)
                        parents.pop()

                if operation == "QUALITY_BUILD" and "observe" in inspect.signature(original).parameters:
                    previous = kwargs.get("observe")
                    def observe(name, event):
                        point(name, event)
                        if previous:
                            previous(name, event)
                    kwargs = {**kwargs, "observe": observe}
                try:
                    value = original(*args, **kwargs)
                except BaseException:
                    try:
                        emit("ERROR", operation, identity, parent)
                    except Exception:
                        pass  # Preserve the original analysis failure if diagnostics also fail.
                    raise
                else:
                    emit("END", operation, identity, parent)
                    return value
                finally:
                    del parents[depth:]
            return measured

        for owner, name, operation in targets:
            original = getattr(owner, name)
            setattr(owner, name, instrument(original, operation))
            restore.callback(setattr, owner, name, original)
        yield
