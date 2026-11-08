"""Opt-in SCALE diagnostics for one owned coordinator process.

Only fixed aggregate labels and numeric data reach the receipt. The probe
observes existing parser and publication operations and restores all hooks.
"""
import gc
import inspect
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from pathlib import Path, PurePosixPath

from scripts.scale_linux_resources import cgroup_diagnostics, namespace_rss

SCHEMA = "projecttrace-scale-diagnostic-v1"
PHASES = frozenset(("START", "VALIDATING", "PARSING", "ANALYZING", "EXTRACTING_CLAIMS", "VERIFYING",
                    "BUILDING_EVIDENCE", "CORRELATING", "FINALIZING", "OTHER", "NATIVE_PARTITION"))
SPANS = frozenset(("PARTITION_PARSE", "CACHE_LOOKUP", "OBSERVATION_SPILL", "CACHE_WRITE",
                   "NATIVE_HELPER_TRANSPORT", "SYNTAX_HELPER_TRANSPORT"))
TYPES = frozenset(("PYTHON", "TYPESCRIPT", "JAVASCRIPT", "JAVA", "YAML", "JSON", "DOCKERFILE", "TERRAFORM", "OTHER"))
ROUTES = frozenset(("NO_HCL_DOCKERFILE", "NO_HCL_YAML", "NO_HCL_JSON", "NO_HCL_CONFIG_MIXED",
                    "HCL_TERRAFORM", "HCL_MIXED", "HCL_UNNEEDED", "NO_HCL_MISROUTE",
                    "NATIVE", "SYNTAX", "RUNTIME_PROBE", "LEXICAL", "OPENAPI", "IDENTITY", "OTHER"))
KINDS = {"native": "NATIVE", "languages": "SYNTAX", "probe": "RUNTIME_PROBE",
         "identity": "IDENTITY", "openapi_batch": "OPENAPI"}
ERRORS = frozenset(("ANALYSIS_TIME_BUDGET", "GLOBAL_CHECKPOINT_BUDGET", "IAC_PARSER_NOT_PREPARED",
                    "HELPER_TIMEOUT", "HELPER_PROCESS_LIMIT", "ISOLATION_STARTUP", "ISOLATION_NOT_ATTESTED",
                    "CANCELLED"))
MEMORY_STATS = ("anon", "file", "kernel", "shmem", "pgscan", "pgsteal", "pgscan_direct", "pgsteal_direct",
                "workingset_refault_file", "pgmajfault")
COUNTERS = {"memory.stat": MEMORY_STATS[4:], "memory.events": ("low", "high", "max", "oom", "oom_kill"),
            "memory.events.local": ("low", "high", "max", "oom", "oom_kill"),
            "cpu.stat": ("usage_usec", "user_usec", "system_usec", "nr_throttled", "throttled_usec"),
            "io.stat": ("rbytes", "wbytes", "rios", "wios"),
            **dict.fromkeys(("memory.pressure", "cpu.pressure", "io.pressure"), ("some", "full"))}
GAUGES = ("memory.current", "memory.peak", "memory.max", "memory.swap.current", "memory.swap.max",
          "pids.current", "pids.max", "cpu.max")
MAX_RECEIPT_BYTES = 196_608


def category(path):
    if not isinstance(path, str):
        return "OTHER"
    name = PurePosixPath(path)
    suffix = name.suffix.lower()
    if suffix == ".tf" or path.endswith(".tf.json"):
        return "TERRAFORM"
    if name.name.startswith("Dockerfile"):
        return "DOCKERFILE"
    return {".py": "PYTHON", ".ts": "TYPESCRIPT", ".tsx": "TYPESCRIPT", ".java": "JAVA",
            ".js": "JAVASCRIPT", ".jsx": "JAVASCRIPT", ".mjs": "JAVASCRIPT", ".cjs": "JAVASCRIPT",
            ".yml": "YAML", ".yaml": "YAML", ".json": "JSON"}.get(suffix, "OTHER")


def route(operation, files):
    if operation not in ("iac", "iac_without_hcl"):
        return KINDS.get(operation, "LEXICAL" if operation.startswith("lexical_") else "OTHER")
    types = {category(path) for path in files}
    terraform = "TERRAFORM" in types
    if operation == "iac":
        return ("HCL_TERRAFORM" if types == {"TERRAFORM"} else "HCL_MIXED") if terraform else "HCL_UNNEEDED"
    if terraform:
        return "NO_HCL_MISROUTE"
    for kind in ("DOCKERFILE", "YAML", "JSON"):
        if types == {kind}:
            return "NO_HCL_" + kind
    return "NO_HCL_CONFIG_MIXED"


def cgroup_root():
    try:
        entry = next(row[3:] for row in Path("/proc/self/cgroup").read_text().splitlines() if row.startswith("0::"))
        return Path("/sys/fs/cgroup") / entry.lstrip("/")
    except (OSError, StopIteration):
        return None


def snapshot(root):
    def read(name):
        try:
            return (root / name).read_text().strip() if root is not None else None
        except OSError:
            return None

    def mapping(name, raw):
        try:
            if isinstance(raw, dict):
                return raw
            if name.startswith("memory.events"):
                return {key: int(n) for key, n in (row.split() for row in raw.splitlines())}
            if name.endswith(".pressure"):
                return {row.split()[0]: int(row.rsplit("total=", 1)[1]) for row in raw.splitlines()}
            if name == "io.stat":
                io = Counter()
                for row in raw.splitlines():
                    io.update({key: int(n) for key, n in (v.split("=") for v in row.split()[1:])})
                return io
        except (AttributeError, ValueError, IndexError):
            pass
        return {}

    known = cgroup_diagnostics(root) if root is not None else {}
    values = {}
    for name, keys in (COUNTERS | {"memory.stat": MEMORY_STATS}).items():
        raw = known[name] if name in known else read(name)
        mapped = mapping(name, raw)
        values[name] = {key: mapped.get(key) for key in keys}
    for name in GAUGES:
        value = read(name)
        values[name] = int(value) if value and value.isdecimal() else value
    values["rss"] = {key: value for key, value in namespace_rss(Path("/proc"), os.getpid()).items()
                     if key in ("coordinator_rss_bytes", "child_rss_bytes", "namespace_rss_complete")}
    return values


def counter_delta(before, after):
    return {name: {key: (b - a if isinstance(a := before[name][key], int)
                        and isinstance(b := after[name][key], int) and b >= a else None)
                   for key in keys} for name, keys in COUNTERS.items()}


class Diagnostic:
    def __init__(self, path, *, revision, cache, source_sha256, slice_sha256, image_sha256):
        if revision not in {"baseline", "candidate"} or cache not in {"cold", "warm", "fixture"}:
            raise ValueError("Invalid diagnostic identity")
        digests = (source_sha256, slice_sha256, image_sha256)
        if any(not re.fullmatch(r"[0-9a-f]{64}", item) for item in digests):
            raise ValueError("Diagnostic identity requires verified SHA-256 values")
        self.path = path
        self.identity = dict(zip(("source_sha256", "slice_sha256", "image_sha256"), digests))
        self.identity.update(revision=revision, cache=cache)
        self.started = time.perf_counter_ns()
        self.stage = "START"
        self.root = cgroup_root()
        self.start = snapshot(self.root)
        self.boundary = self.start
        self.stage_started = self.started
        self.cgroup = {}
        self.stage_wall = Counter()
        self.routes = defaultdict(Counter)
        self.packet_types = defaultdict(Counter)
        self.spans = defaultdict(Counter)
        self.gc = defaultdict(Counter)
        self.totals = Counter()
        self.local = threading.local()
        self.lock = threading.RLock()
        self.active_parser_invokes = 0
        self.parser_union_start = None

    def store(self, target, key, **values):
        with self.lock:
            target[key].update(values)

    @contextmanager
    def timed(self, phase):
        previous = getattr(self.local, "phase", None)
        self.local.phase = phase
        start, cpu = time.perf_counter_ns(), time.thread_time_ns()
        try:
            yield
        finally:
            elapsed = time.perf_counter_ns() - start
            thread = time.thread_time_ns() - cpu
            self.local.phase = previous
            self.store(self.spans, phase, calls=1, wall_ns=elapsed, thread_cpu_ns=thread)

    def collect_gc(self, event, info):
        gen = info["generation"]
        if event == "start":
            self.local.collection = (gen, getattr(self.local, "phase", None) or self.stage,
                                     time.perf_counter_ns(), time.thread_time_ns())
        elif (entry := getattr(self.local, "collection", None)) is not None:
            gen, phase, start, cpu = entry
            self.local.collection = None
            elapsed, cpu_elapsed = time.perf_counter_ns()-start, time.thread_time_ns()-cpu
            self.store(self.gc, f"{phase}/{gen}", count=1, wall_ns=elapsed, thread_cpu_ns=cpu_elapsed)
            packet = getattr(self.local, "decode_gc", None)
            if packet is not None:
                packet.update(gc_count=1, gc_wall_ns=elapsed, gc_cpu_ns=cpu_elapsed)

    def change_stage(self, stage):
        stage = stage if stage in PHASES else "OTHER"
        if stage == self.stage:
            return
        end = snapshot(self.root)
        now = time.perf_counter_ns()
        self.stage_wall[self.stage] += now - self.stage_started
        self.resource_interval(self.stage, self.boundary, end)
        self.stage, self.boundary, self.stage_started = stage, end, now
        self.write("RUNNING")

    def resource_interval(self, name, before, after):
        deltas = counter_delta(before, after)
        prior = self.cgroup.get(name)
        if prior is not None:
            for field, counters in deltas.items():
                for key, value in counters.items():
                    earlier = prior["delta"][field][key]
                    counters[key] = value + earlier if value is not None and earlier is not None else None
        self.cgroup[name] = {"start": prior["start"] if prior else before, "end": after, "delta": deltas,
                             "intervals": 1 + (prior["intervals"] if prior else 0)}

    def finish(self, state, code=None):
        end = snapshot(self.root)
        self.stage_wall[self.stage] += time.perf_counter_ns() - self.stage_started
        self.resource_interval(self.stage, self.boundary, end)
        self.write(state, code)

    def write(self, state, error=None):
        try:
            with self.lock:
                packet_rows = {key: {**row, "logical_nodes": row.get("logical_nodes") if row.get("node_samples") else None}
                               for key, row in self.packet_types.items()}
                routes = {key: {**row, "grammar_observations": row["grammar_observations"],
                                "grammars_prepared": row["grammars_prepared"] if row["grammar_observations"] else None}
                          for key, row in self.routes.items()}
                data = {"schema": SCHEMA, "identity": self.identity, "state": state, "failure_code": error,
                        "stage": self.stage, "elapsed_ns": time.perf_counter_ns()-self.started,
                        "routes": routes, "packets": packet_rows, "spans": self.spans, "gc": self.gc,
                        "counts": self.totals, "stage_wall_ns": self.stage_wall,
                        "cgroup": self.cgroup, "cgroup_scope": "PROCESS_CGROUP_V2" if self.root else None,
                        "overhead": {"external_matched_control_required": True}}
                payload = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
            if len(payload) > MAX_RECEIPT_BYTES:
                raise ValueError("Diagnostic aggregate exceeds its fixed byte budget")
            temp = self.path.with_suffix(".pending")
            temp.write_bytes(payload)
            temp.replace(self.path)
        except (OSError, ValueError):
            self.totals["write_errors"] += 1

    def install(self, stack):
        from sqlalchemy.orm import Session

        from analyzers import infrastructure, isolated_analysis, languages, parser_protocol, sandbox
        from analyzers.performance import Performance

        def patch(owner, name, replacement):
            original = getattr(owner, name)
            setattr(owner, name, replacement)
            stack.callback(setattr, owner, name, original)

        original_switch = Performance.switch
        def switch(owner, stage):
            original_switch(owner, stage)
            self.change_stage(stage)
        patch(Performance, "switch", switch)
        original_record = Performance.record
        def record(owner, component, seconds, *args, **kw):
            original_record(owner, component, seconds, *args, **kw)
            if component in SPANS:
                self.store(self.spans, component, calls=1, wall_ns=round(seconds*1e9))
        patch(Performance, "record", record)
        original_commit = Session.commit
        def commit(owner):
            with self.timed("DB_COMMIT"):
                return original_commit(owner)
        patch(Session, "commit", commit)

        original_invoke = sandbox.invoke
        def invoke(operation, value, **kw):
            files = value.get("files", {}) if isinstance(value, dict) else {}
            name = route(operation, files)
            row = Counter(requests=1, requested_files=len(files))
            self.local.worker = (operation, row)
            tracked = operation in ("iac", "iac_without_hcl", "native", "languages")
            with self.lock:
                start = time.perf_counter_ns()
                if tracked:
                    if self.active_parser_invokes == 0:
                        self.parser_union_start = start
                    self.active_parser_invokes += 1
            try:
                raw, failure = original_invoke(operation, value, **kw)
                row["failed"] += bool(failure)
                if name == "NO_HCL_MISROUTE" and len(raw) < 256:
                    try:
                        reply = json.loads(raw)
                        row["rejected"] += reply == {"ok": False, "code": "IAC_PARSER_NOT_PREPARED"}
                    except (ValueError, TypeError):
                        pass
                return raw, failure
            except BaseException:
                row["failed"] += 1
                raise
            finally:
                self.local.worker = None
                self.local.last_route = name
                with self.lock:
                    end = time.perf_counter_ns()
                    row["invoke_wall_ns"] += end - start
                    self.routes[name].update(row)
                    if tracked:
                        self.spans["PARSER_INVOKE_SUM"].update(calls=1, wall_ns=end-start)
                        self.active_parser_invokes -= 1
                        if self.active_parser_invokes == 0:
                            self.spans["PARSER_INVOKE_UNION"].update(calls=1, wall_ns=end-self.parser_union_start)
                if operation in ("iac", "iac_without_hcl"):
                    self.totals["iac_starts"] += row["starts"]
        patch(sandbox, "invoke", invoke)

        original_bounded = sandbox.bounded_process
        def bounded(command, payload, **kw):
            active = getattr(self.local, "worker", None)
            if active is None:
                return original_bounded(command, payload, **kw)
            operation, row = active
            iac = operation in ("iac", "iac_without_hcl")
            installed = str(Path(sandbox.__file__).with_name("isolated_worker.py"))
            if iac and command == [sys.executable, "-I", "-B", installed, operation]:
                command = [*command[:3], str(Path(__file__).with_name("scale_diagnostic_worker.py")), *command[3:]]
            result = original_bounded(command, payload, **kw)
            if iac:
                self.observe_proof(result[0], row)
            return result
        patch(sandbox, "bounded_process", bounded)

        observer = self
        class WorkerProcess(subprocess.Popen):
            def __init__(owner, *args, **kw):
                active = getattr(observer.local, "worker", None)
                owner.diagnostic = active[1] if active is not None else None
                owner.diagnostic_started = time.perf_counter_ns()
                super().__init__(*args, **kw)
                if owner.diagnostic is not None:
                    owner.diagnostic["starts"] += 1

            def _try_wait(owner, flags):
                if owner.diagnostic is None:
                    return super()._try_wait(flags)
                try:
                    pid, status, usage = os.wait4(owner.pid, flags)
                except ChildProcessError:
                    return owner.pid, 0
                if pid:
                    owner.diagnostic.update(reaped=1, worker_wall_ns=time.perf_counter_ns()-owner.diagnostic_started,
                        worker_cpu_ns=round((usage.ru_utime+usage.ru_stime)*1e9),
                        worker_rss_bytes_sum=usage.ru_maxrss*1024)
                return pid, status
        patch(subprocess, "Popen", WorkerProcess)

        completed = parser_protocol.completed_packets
        def gate(kind):
            def wrapper(output, files, *args, **kw):
                name = getattr(self.local, "last_route", "OTHER")
                self.local.packet = (kind, "OTHER")
                self.local.expected_files = files
                self.store(self.spans, f"{kind}_GATE", bytes=len(output))
                expand = kw.get("expand")
                if expand is not None:
                    def expansion(path, value):
                        start = time.perf_counter_ns()
                        try:
                            return expand(path, value)
                        finally:
                            self.store(self.packet_types, f"{kind}/{category(path)}",
                                       expand_wall_ns=time.perf_counter_ns()-start)
                    kw["expand"] = expansion
                try:
                    with self.timed(f"{kind}_GATE"):
                        result = completed(output, files, *args, **kw)
                    for path in result:
                        self.store(self.packet_types, f"{kind}/{category(path)}", admitted=1)
                    self.store(self.routes, name, admitted_packets=len(result))
                    return result
                except BaseException:
                    self.store(self.routes, name, gate_rejected=1)
                    raise
                finally:
                    self.local.packet = self.local.expected_files = None
            return wrapper
        for owner, kind in ((isolated_analysis, "NATIVE"), (languages, "SYNTAX"), (infrastructure, "IAC")):
            patch(owner, "completed_packets", gate(kind))
        decode = parser_protocol.decode_packet
        def decode_frame(raw):
            if getattr(self.local, "packet", None) is None:
                return decode(raw)
            kind, _ = self.local.packet
            label = "OTHER"
            self.local.packet = kind, label
            start, cpu = time.perf_counter_ns(), time.thread_time_ns()
            previous, self.local.phase = getattr(self.local, "phase", None), f"{kind}_DECODE"
            self.local.decode_gc = Counter()
            self.local.guard_start, self.local.guard_elapsed = start, None
            result = None
            try:
                result = decode(raw)
                return result
            finally:
                wall, thread = time.perf_counter_ns()-start, time.thread_time_ns()-cpu
                self.local.phase = previous
                extras = self.local.decode_gc
                if self.local.guard_elapsed is not None:
                    extras.update(guard_observations=1, decoder_guard_wall_ns=self.local.guard_elapsed)
                self.local.decode_gc = self.local.guard_start = None
                if isinstance(result, dict) and isinstance(path := result.get("path"), str) and path in self.local.expected_files:
                    label = category(path)
                self.local.packet = kind, label
                self.store(self.packet_types, f"{kind}/{label}", frames=1, json_bytes=len(raw),
                           decode_wall_ns=wall, decode_cpu_ns=thread, **extras)
        patch(parser_protocol, "decode_packet", decode_frame)
        sanitize = parser_protocol.metadata
        def privacy(value):
            if getattr(self.local, "packet", None) is None:
                return sanitize(value)
            kind, label = self.local.packet
            start, cpu = time.perf_counter_ns(), time.thread_time_ns()
            previous, self.local.phase = getattr(self.local, "phase", None), f"{kind}_PRIVACY"
            try:
                result = sanitize(value)
                self.store(self.packet_types, f"{kind}/{label}", validated=1)
                return result
            finally:
                self.local.phase = previous
                self.store(self.packet_types, f"{kind}/{label}", privacy_wall_ns=time.perf_counter_ns()-start,
                           privacy_cpu_ns=time.thread_time_ns()-cpu)
        patch(parser_protocol, "metadata", privacy)
        native = isolated_analysis.native
        self.monitor(stack, native, sanitize, decode)

        def native_partition(*args, **kwargs):
            before, starts = snapshot(self.root), self.totals["iac_starts"]
            try:
                result = native(*args, **kwargs)
                if result[7] and len(result[6]) == result[7]:
                    self.totals["cache_only_partitions"] += 1
                return result
            finally:
                self.local.materialize = self.local.phase = None
                self.resource_interval("NATIVE_PARTITION", before, snapshot(self.root))
                if self.totals["iac_starts"] == starts:
                    self.totals["partitions_without_iac_launch"] += 1
                self.totals["native_partitions"] += 1
                if self.totals["native_partitions"] % 16 == 0:
                    self.write("RUNNING")
        patch(isolated_analysis, "native", native_partition)
        gc.callbacks.append(self.collect_gc)
        stack.callback(gc.callbacks.remove, self.collect_gc)

    def observe_proof(self, output, row):
        end = output.find(b"\n", 0, 4097)
        if end < 0:
            return
        try:
            details = json.loads(output[:end]).get("scale_diagnostic", {})
            if type(details.get("grammar_prepared")) is bool:
                row["grammar_observations"] += 1
                row["grammars_prepared"] += details["grammar_prepared"]
            for key in ("prepare_ns", "containment_ns", "attestation_ns"):
                value = details.get(key)
                if type(value) is int and 0 <= value <= 60_000_000_000:
                    row[key] += value
        except (ValueError, AttributeError):
            pass

    def monitor(self, stack, native, sanitize, decode):
        def line_at(function, prefix):
            lines, first = inspect.getsourcelines(function)
            return next(first+i for i, line in enumerate(lines) if line.strip().startswith(prefix))
        combined = line_at(native, "combined = ")
        guard = line_at(decode, "decoder = json.JSONDecoder")
        monitoring = sys.monitoring
        tool = next(n for n in range(6) if monitoring.get_tool(n) is None)
        monitoring.use_tool_id(tool, "scale-diagnostic")
        stack.callback(monitoring.free_tool_id, tool)
        event = monitoring.events

        def line(code, number):
            if code is decode.__code__:
                if number != guard:
                    return monitoring.DISABLE
                if (started := getattr(self.local, "guard_start", None)) is not None:
                    self.local.guard_elapsed = time.perf_counter_ns() - started
                return None
            if number != combined:
                return monitoring.DISABLE
            self.local.materialize = (time.perf_counter_ns(), time.thread_time_ns())
            self.local.phase = "COORDINATOR_MATERIALIZE"
            return None

        def returned(code, offset, result):
            if code is sanitize.__code__:
                active = getattr(self.local, "packet", None)
                if active and isinstance(nodes := sys._getframe(1).f_locals.get("nodes"), int):
                    self.store(self.packet_types, "/".join(active), node_samples=1, logical_nodes=nodes)
                return
            mark = getattr(self.local, "materialize", None)
            if mark is not None:
                self.store(self.spans, "COORDINATOR_MATERIALIZE", calls=1, wall_ns=time.perf_counter_ns()-mark[0],
                           thread_cpu_ns=time.thread_time_ns()-mark[1])
            self.local.materialize = self.local.phase = None

        for kind, callback in ((event.LINE, line), (event.PY_RETURN, returned)):
            monitoring.register_callback(tool, kind, callback)
            stack.callback(monitoring.register_callback, tool, kind, None)
        for code, mask in ((native.__code__, event.LINE | event.PY_RETURN),
                           (sanitize.__code__, event.PY_RETURN), (decode.__code__, event.LINE)):
            monitoring.set_local_events(tool, code, mask)
            stack.callback(monitoring.set_local_events, tool, code, 0)


@contextmanager
def diagnostic(path, **identity):
    if path is None:
        yield
        return
    with ExitStack() as stack:
        observer = Diagnostic(path, **identity)
        observer.install(stack)
        observer.write("RUNNING")
        try:
            yield
        except BaseException as error:
            code = getattr(error, "code", None)
            observer.finish("FAILED", code if isinstance(code, str) and code in ERRORS else "OTHER")
            raise
        else:
            observer.finish("COMPLETED")
