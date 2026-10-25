"""SEC-002 owned parser transport. No repository commands or paths are executed.

Linux parsing defaults to required containment. An explicit non-production
development mode retains portable behavior without claiming OS isolation.
"""

import ctypes
import errno
import json
import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

POLICY = "linux-landlock-seccomp-v2-lexical"
ACTIVE = False  # Set only by the owned bootstrap after enforcement and probes.


class SandboxFailure(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(f"Parser isolation unavailable or stopped ({code}); inspect SEC-002 deployment prerequisites.")


def mode():
    selected = os.getenv("PROJECTTRACE_PARSER_ISOLATION", "required" if sys.platform == "linux" else "development")
    if selected not in {"required", "development"}:
        raise SandboxFailure("ISOLATION_CONFIGURATION")
    if os.getenv("APP_ENV") == "production" and (selected != "required" or sys.platform != "linux"):
        raise SandboxFailure("ISOLATION_REQUIRED")
    return selected


def required():
    return mode() == "required" and not ACTIVE


def cache_policy():
    # Tag import-time signatures without turning an unrelated module import
    # into parsing. Invalid/production downgrade modes still fail at entry.
    selected = os.getenv("PROJECTTRACE_PARSER_ISOLATION", "required" if sys.platform == "linux" else "development")
    return POLICY if selected == "required" or os.getenv("APP_ENV") == "production" else "development-uncontained-v2-lexical"


def status():
    return {"policy": POLICY, "mode": mode(), "enforcement": "PER_WORKER_DENIAL_PROBES" if mode() == "required"
            else "DEVELOPMENT_UNCONTAINED", "windows_equivalent": False}


def decode_packet(raw):
    """Bounded pure-Python JSON scanner for the untrusted helper IPC boundary."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if len(raw) > 32_000_000:
        raise SandboxFailure("HELPER_PROTOCOL_BUDGET")
    depth, quoted, escaped, nodes = 0, False, False, 0
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            nodes += 1
            if depth > 100:
                raise SandboxFailure("HELPER_PROTOCOL_DEPTH")
        elif char in "]}":
            depth -= 1
        elif char in ",:":
            nodes += 1
        if nodes > 1_000_000:
            raise SandboxFailure("HELPER_PROTOCOL_NODES")
    decoder = json.JSONDecoder()
    decoder.parse_string = json.decoder.py_scanstring
    decoder.scan_once = json.scanner.py_make_scanner(decoder)
    return decoder.decode(raw)


def bounded_process(command, payload, *, seconds, maximum, environment):
    """Drain pipes incrementally; neither stdout flooding nor stderr can grow RAM unbounded."""
    started = time.monotonic()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=environment, cwd="/", close_fds=True, start_new_session=True)
    output, written = bytearray(), 0
    reason = None
    with selectors.DefaultSelector() as selector:
        for stream, event in ((process.stdin, selectors.EVENT_WRITE), (process.stdout, selectors.EVENT_READ),
                              (process.stderr, selectors.EVENT_READ)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, event)
        try:
            while selector.get_map():
                if time.monotonic() - started > seconds:
                    reason = "HELPER_TIMEOUT"
                    break
                for key, _ in selector.select(0.05):
                    stream = key.fileobj
                    if stream is process.stdin:
                        try:
                            written += os.write(stream.fileno(), payload[written:written + 65536])
                        except BrokenPipeError:
                            written = len(payload)
                        if written == len(payload):
                            selector.unregister(stream)
                            stream.close()
                    else:
                        data = os.read(stream.fileno(), 65536)
                        if not data:
                            selector.unregister(stream)
                            stream.close()
                        elif stream is process.stdout:
                            if len(output) + len(data) > maximum:
                                raise SandboxFailure("HELPER_OUTPUT_BUDGET")
                            output.extend(data)
                        # stderr is drained and discarded: never export raw exception/source text.
            if reason is None:
                try:
                    process.wait(timeout=max(0.05, seconds - (time.monotonic() - started)))
                except subprocess.TimeoutExpired:
                    reason = "HELPER_TIMEOUT"
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                if not stream.closed:
                    stream.close()
    return bytes(output), reason or ("HELPER_PROCESS_LIMIT" if process.returncode else None)


def invoke(operation, value, *, seconds=30, maximum=16_000_000, input_maximum=32_000_000):
    if sys.platform != "linux":
        raise SandboxFailure("LINUX_REQUIRED")
    payload = json.dumps({"operation": operation, "value": value}, ensure_ascii=False).encode()
    if len(payload) > input_maximum:
        raise SandboxFailure("HELPER_INPUT_BUDGET")
    try:
        output, failure = bounded_process(
            [sys.executable, "-I", "-B", str(Path(__file__).with_name("isolated_worker.py")), operation], payload,
            seconds=seconds, maximum=maximum + 4096,
            environment={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PROJECTTRACE_PARSER_ISOLATION": "required"},
        )
    except OSError:
        raise SandboxFailure("ISOLATION_STARTUP") from None
    header, separator, packets = output.partition(b"\n")
    validate_proof(header if separator else b"")
    return packets, failure


def validate_proof(header):
    """Shared attestation validation for single-packet and streaming transports."""
    try:
        proof = decode_packet(header) if header and len(header) <= 4096 else {}
    except ValueError:
        proof = {}
    if not isinstance(proof, dict):
        proof = {}
    if proof.get("policy") != POLICY or proof.get("enforced") is not True or proof.get("denials") != ["filesystem", "network", "exec", "metadata"]:
        code = proof.get("failure", "")
        if not isinstance(code, str) or not code.isupper() or len(code) > 60:
            code = "ISOLATION_NOT_ATTESTED"
        raise SandboxFailure(code or "ISOLATION_NOT_ATTESTED")
    return proof


def call(operation, value, **limits):
    packets, failure = invoke(operation, value, **limits)
    if failure:
        raise SandboxFailure(failure)
    try:
        result = decode_packet(packets)
    except ValueError:
        raise SandboxFailure("HELPER_PROTOCOL") from None
    if isinstance(result, dict) and result.get("ok") is False and result.get("code") == "SOURCE_SYNTAX_FAILED":
        raise SandboxFailure("SOURCE_SYNTAX_FAILED")
    if isinstance(result, dict) and result.get("ok") is False and result.get("code") in {
        "CODEOWNERS_SOURCE_BUDGET", "CODEOWNERS_INPUT_BUDGET", "CODEOWNERS_PATTERN_BUDGET", "CODEOWNERS_MATCH_BUDGET",
        "SECTIONS_SOURCE_BUDGET", "LEXICAL_FILE_BUDGET", "LEXICAL_DIFF_BUDGET",
    }:
        raise SandboxFailure(result["code"])
    if not isinstance(result, dict) or result.get("ok") is not True or "result" not in result:
        raise SandboxFailure("HELPER_OPERATION_FAILED")
    value = result["result"]
    if operation.startswith("lexical_") or operation in {"python", "identity", "inventory", "documentation", "coverage", "metrics", "structure", "flows"}:
        from analyzers.sanitization import metadata
        try:
            value = metadata(value)
        except ValueError:
            raise SandboxFailure("HELPER_UNSAFE_METADATA") from None
    return value


def parse_json(source):
    if not required():
        return json.loads(source)
    try:
        return call("json", {"source": source})
    except SandboxFailure as error:
        if error.code == "SOURCE_SYNTAX_FAILED":
            raise ValueError("Repository JSON syntax is invalid") from None
        raise


def require_runtime():
    # A real child installs controls and demonstrates denial, even before a cache-only read.
    if required():
        return call("probe", {})
    return status()


def install(read_paths):
    """Irreversible Linux Landlock filesystem policy plus seccomp syscall allowlist."""
    import platform
    import resource

    if sys.platform != "linux" or platform.machine() not in {"x86_64", "aarch64"}:
        raise SandboxFailure("UNSUPPORTED_KERNEL_ARCH")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    abi = libc.syscall(444, 0, 0, 1)
    if abi < 3:
        raise SandboxFailure("LANDLOCK_ABI_3_REQUIRED")

    class CapHeader(ctypes.Structure):
        _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]

    class CapData(ctypes.Structure):
        _fields_ = [("effective", ctypes.c_uint32), ("permitted", ctypes.c_uint32), ("inheritable", ctypes.c_uint32)]

    if libc.capset(ctypes.byref(CapHeader(0x20080522, 0)), ctypes.byref((CapData * 2)())) != 0:
        raise SandboxFailure("CAPABILITY_DROP_FAILED")
    if libc.prctl(4, 0, 0, 0, 0) != 0 or libc.prctl(38, 1, 0, 0, 0) != 0:
        raise SandboxFailure("NO_NEW_PRIVILEGES_FAILED")
    with open("/proc/self/status") as stream:
        caps = {line.split(":")[0]: int(line.split()[1], 16) for line in stream
                if line.startswith(("CapEff:", "CapPrm:", "CapInh:"))}
    if any(caps.values()) or len(caps) != 3:
        raise SandboxFailure("CAPABILITIES_REMAIN")
    # Stdio are the only inherited descriptors. All input is supplied through stdin.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    library = ctypes.CDLL("libseccomp.so.2", use_errno=True)

    class Ruleset(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]

    class PathRule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int)]

    rules = libc.syscall(444, ctypes.byref(Ruleset((1 << 15) - 1)), ctypes.sizeof(Ruleset), 0)
    if rules < 0:
        raise SandboxFailure("LANDLOCK_CREATE_FAILED")
    try:
        for path in sorted(set(read_paths)):
            descriptor = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                access = (1 << 2) | ((1 << 3) if os.path.isdir(path) else 0)
                rule = PathRule(access, descriptor)
                if libc.syscall(445, rules, 1, ctypes.byref(rule), 0) != 0:
                    raise SandboxFailure("LANDLOCK_ALLOWLIST_FAILED")
            finally:
                os.close(descriptor)
        if libc.syscall(446, rules, 0) != 0:
            raise SandboxFailure("LANDLOCK_ENFORCEMENT_FAILED")
    finally:
        os.close(rules)
    os.closerange(3, 1_048_576)

    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    library.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p]
    context = library.seccomp_init(0x00050000 | errno.EPERM)
    if not context:
        raise SandboxFailure("SECCOMP_CREATE_FAILED")
    try:
        for name in ("read", "write", "writev", "readv", "close", "exit", "exit_group", "brk", "mmap", "mprotect",
                     "munmap", "mremap", "madvise", "fstat", "lseek", "pread64",
                     "getdents64", "getpid", "gettid", "futex", "clock_gettime", "getrusage", "getrandom",
                     "rt_sigaction", "rt_sigprocmask", "rt_sigreturn", "sigaltstack", "sched_yield", "restart_syscall"):
            number = library.seccomp_syscall_resolve_name(name.encode())
            if number >= 0 and library.seccomp_rule_add(context, 0x7fff0000, number, 0) != 0:
                raise SandboxFailure("SECCOMP_RULE_FAILED")
        class Compare(ctypes.Structure):
            _fields_ = [("arg", ctypes.c_uint), ("op", ctypes.c_int), ("a", ctypes.c_uint64), ("b", ctypes.c_uint64)]
        # Landlock intentionally does not mediate O_PATH. Deny it and all
        # write/create/truncate/append opens before VFS to close metadata and
        # mutation bypasses; allow only readonly runtime opens under Landlock.
        forbidden = os.O_ACCMODE | os.O_CREAT | os.O_TRUNC | os.O_APPEND | os.O_PATH | 0x400000
        for name, argument in (("open", 1), ("openat", 2)):
            number = library.seccomp_syscall_resolve_name(name.encode())
            compare = Compare(argument, 7, forbidden, 0)  # SCMP_CMP_MASKED_EQ
            if number >= 0 and library.seccomp_rule_add_array(context, 0x7fff0000, number, 1, ctypes.byref(compare)) != 0:
                raise SandboxFailure("SECCOMP_RULE_FAILED")
        # F_SETOWN/F_SETFL could deliver asynchronous signals to another process.
        for command in (1, 2, 3):  # F_GETFD, F_SETFD, F_GETFL
            compare = Compare(1, 4, command, 0)
            if library.seccomp_rule_add_array(context, 0x7fff0000,
                    library.seccomp_syscall_resolve_name(b"fcntl"), 1, ctypes.byref(compare)) != 0:
                raise SandboxFailure("SECCOMP_RULE_FAILED")
        for query in (3, 21, 39):  # GET_DUMPABLE, GET_SECCOMP, GET_NO_NEW_PRIVS only.
            compare = Compare(0, 4, query, 0)
            if library.seccomp_rule_add_array(context, 0x7fff0000,
                                             library.seccomp_syscall_resolve_name(b"prctl"), 1, ctypes.byref(compare)) != 0:
                raise SandboxFailure("SECCOMP_RULE_FAILED")
        if library.seccomp_load(context) != 0:
            raise SandboxFailure("SECCOMP_ENFORCEMENT_FAILED")
    finally:
        library.seccomp_release(context)
    if libc.prctl(39, 0, 0, 0, 0) != 1 or libc.prctl(21, 0, 0, 0, 0) != 2 or libc.prctl(3, 0, 0, 0, 0) != 0:
        raise SandboxFailure("KERNEL_STATE_MISMATCH")
    return int(abi)
