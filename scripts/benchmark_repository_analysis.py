"""Isolated static-analysis benchmark; never imports or executes fixture code.

Use a new empty --output directory. Cold means no ProjectTrace parser cache;
it does not mean the operating system's filesystem cache has been cleared.
"""

import argparse
import cProfile
import ctypes
import hashlib
import json
import os
import pstats
import subprocess
import sys
import threading
import time
import zipfile
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def windows_measurement_api():
    """Compile measurement layouts once; sampling must not dominate the work."""
    from ctypes import wintypes

    class Memory(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("faults", wintypes.DWORD),
            *[
                (name, ctypes.c_size_t)
                for name in (
                    "peak",
                    "rss",
                    "peak_paged",
                    "paged",
                    "peak_nonpaged",
                    "nonpaged",
                    "pagefile",
                    "peak_pagefile",
                )
            ],
        ]

    kernel = ctypes.WinDLL("kernel32")
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.c_void_p] * 4)]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    psapi = ctypes.WinDLL("psapi")
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    class Entry(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("pid", wintypes.DWORD),
            ("heap", ctypes.c_size_t), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
            ("parent", wintypes.DWORD), ("priority", wintypes.LONG), ("flags", wintypes.DWORD),
            ("name", wintypes.WCHAR * 260),
        ]
    return kernel, psapi, Memory, Entry


def process_stats(handle=None):
    if os.name != "nt":
        import resource

        row = resource.getrusage(resource.RUSAGE_SELF)
        return {"cpu_seconds": row.ru_utime + row.ru_stime, "rss_bytes": row.ru_maxrss * 1024}
    kernel, psapi, Memory, _ = windows_measurement_api()
    handle = handle or kernel.GetCurrentProcess()
    memory = Memory(cb=ctypes.sizeof(Memory))
    times = [ctypes.c_ulonglong() for _ in range(4)]
    if not kernel.GetProcessTimes(handle, *(ctypes.byref(v) for v in times)):
        return None
    psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb)
    return {
        "cpu_seconds": (times[2].value + times[3].value) / 10_000_000,
        "rss_bytes": memory.rss,
        "peak_rss_bytes": memory.peak,
    }


class Resources:
    def __init__(self):
        self.children, self.lock, self.stop = [], threading.Lock(), threading.Event()
        self.maximum_rss, self.maximum_helpers, self.helper_cpu = 0, 0, 0.0
        self.helper_seconds, self.helper_calls = 0.0, 0
        self.original = subprocess.Popen
        self.handles = {}
        self.helper_lifetime_cpu = {}
        self.retired_helper_cpu = 0.0

    def owned_descendants(self):
        # Windows venv launchers create another Python process. Include these
        # descendants; measuring only Popen's launcher understates CPU/RSS.
        kernel, _, _, Entry = windows_measurement_api()
        snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            return []
        entry = Entry(size=ctypes.sizeof(Entry))
        parents = {}
        try:
            ok = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            while ok:
                parents[entry.pid] = entry.parent
                ok = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel.CloseHandle(snapshot)
        owned = {child.pid for child in self.children if child.poll() is None}
        while True:
            extended = owned | {pid for pid, parent in parents.items() if parent in owned}
            if extended == owned:
                break
            owned = extended
        for pid in owned:
            if pid not in self.handles:
                handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
                if handle:
                    self.handles[pid] = handle

    def __enter__(self):
        owner = self
        original = self.original

        class MeasuredProcess(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.measured_start, self.measured_done = time.perf_counter(), False
                with owner.lock:
                    owner.children.append(self)

            def wait(self, *args, **kwargs):
                result = super().wait(*args, **kwargs)
                with owner.lock:
                    if not self.measured_done:
                        self.measured_done = True
                        stat = process_stats(self._handle) if os.name == "nt" else None
                        owner.helper_cpu += (stat or {}).get("cpu_seconds", 0)
                        owner.helper_calls += 1
                        owner.helper_seconds += time.perf_counter() - self.measured_start
                return result

        subprocess.Popen = MeasuredProcess
        self.before = process_stats()
        self.started = time.perf_counter()
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.thread.start()
        return self

    def sample(self):
        while not self.stop.is_set():
            rss, active = (process_stats() or {}).get("rss_bytes", 0), 0
            with self.lock:
                for child in self.children:
                    if child.poll() is None:
                        active += 1
                if os.name == "nt":
                    if active:
                        self.owned_descendants()
                    from ctypes import wintypes

                    kernel, _, _, _ = windows_measurement_api()
                    for pid, handle in list(self.handles.items()):
                        stat = process_stats(handle) or {}
                        rss += stat.get("rss_bytes", 0)
                        self.helper_lifetime_cpu[pid] = stat.get("cpu_seconds", self.helper_lifetime_cpu.get(pid, 0))
                        exit_code = wintypes.DWORD()
                        if kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)) and exit_code.value != 259:
                            self.retired_helper_cpu += self.helper_lifetime_cpu.pop(pid, 0)
                            kernel.CloseHandle(handle)
                            del self.handles[pid]
            self.maximum_rss = max(self.maximum_rss, rss)
            self.maximum_helpers = max(self.maximum_helpers, active)
            self.stop.wait(0.1)

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join()
        subprocess.Popen = self.original
        if os.name == "nt":
            kernel, _, _, _ = windows_measurement_api()
            for pid, handle in self.handles.items():
                self.helper_lifetime_cpu[pid] = (process_stats(handle) or {}).get(
                    "cpu_seconds", self.helper_lifetime_cpu.get(pid, 0)
                )
                kernel.CloseHandle(handle)
        after = process_stats()
        wall = time.perf_counter() - self.started
        self.result = {
            "wall_seconds": round(wall, 6),
            "parent_cpu_seconds": round(after["cpu_seconds"] - self.before["cpu_seconds"], 6),
            "helper_cpu_seconds": round(
                self.retired_helper_cpu + sum(self.helper_lifetime_cpu.values()) if os.name == "nt" else self.helper_cpu, 6
            ),
            "helper_cpu_scope": "Owned descendants discovered during 100 ms samples; short-lived undiscovered descendants can be missed.",
            "sampled_process_tree_peak_rss_bytes": self.maximum_rss,
            "parent_lifetime_peak_rss_bytes": after.get("peak_rss_bytes"),
            "helper_concurrency_observed": self.maximum_helpers,
            "helper_calls": self.helper_calls,
            "helper_wall_seconds_overlapping": round(self.helper_seconds, 6),
            "rss_sample_interval_seconds": 0.1,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--files", type=int, default=20)
    parser.add_argument("--functions", type=int, default=10)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--archive", type=Path, help="Authorized ZIP; read selected text as inert data only.")
    parser.add_argument("--component", help="Exact repository-relative directory prefix inside the ZIP.")
    args = parser.parse_args()
    if not 1 <= args.files <= 2000 or not 1 <= args.functions <= 40:
        parser.error("Fixture bounds: 1..2000 files; 1..40 functions per file.")
    if bool(args.archive) != bool(args.component):
        parser.error("--archive and --component must be used together.")
    target = args.output.resolve()
    if target.exists() and any(target.iterdir()):
        parser.error("Output must be an empty isolated directory.")
    target.mkdir(parents=True, exist_ok=True)
    # All settings point to new benchmark-owned objects, before backend imports.
    os.environ.update(
        DATABASE_URL="sqlite:///" + str(target / "benchmark.db"),
        APP_ENV="demo",
        JOB_MODE="sync",
        REPOSITORY_ANALYSIS_SECONDS="900",
        SOURCE_BLOB_DIR=str(target / "blobs"),
        SOURCE_UPLOAD_DIR=str(target / "uploads"),
        ANALYSIS_KEY_FILE=str(target / "key"),
    )
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from cryptography.fernet import Fernet

    os.environ["ANALYSIS_INPUT_KEY"] = Fernet.generate_key().decode()
    from sqlalchemy import event, func, select

    from analyzers.engine import MAX_FILE_BYTES, safe_path
    from backend.db import Base, Grant, Organization, Record, Repository, Session, User, engine
    from backend.jobs import execute_analysis
    from backend.repository_store import RepositoryFiles, capture

    Base.metadata.create_all(engine)
    sources = {
        f"component/app{i:04d}.py": "".join(
            f"def inspect_{j}(value):\n    return eval(value)\n\n" for j in range(args.functions)
        )
        for i in range(args.files)
    }
    archive_hash = None
    if args.archive:
        prefix = str(safe_path(args.component)).rstrip("/") + "/"
        with args.archive.open("rb") as stream:
            archive_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        sources = {}
        with zipfile.ZipFile(args.archive) as archive:
            for entry in sorted(archive.infolist(), key=lambda e: e.filename):
                if not entry.filename.startswith(prefix) or entry.is_dir():
                    continue
                name = str(safe_path(entry.filename))
                if (
                    name in sources
                    or entry.file_size > MAX_FILE_BYTES
                    or entry.file_size / max(entry.compress_size, 1) > 250
                ):
                    raise ValueError("Component entry exceeds path, duplicate, size or compression bounds.")
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Symlinks cannot be benchmark sources.")
                if sum(len(t.encode()) for t in sources.values()) + entry.file_size > 16_000_000:
                    break
                sources[name] = archive.read(entry).decode("utf-8")
                if len(sources) == args.files:
                    break
        if not sources:
            raise ValueError("Authorized component has no eligible text files.")
    receipt = {
        "fixture": "AUTHORIZED_ZIP_COMPONENT_STATIC_ONLY" if args.archive else "NON_EXECUTING_PYTHON_FUNCTIONS",
        "archive_sha256": archive_hash,
        "component": args.component,
        "files": len(sources),
        "functions_per_file": args.functions,
        "source_bytes": sum(len(t.encode()) for t in sources.values()),
        "analysis_limit_seconds": 900,
        "cold_scope": "EMPTY_APPLICATION_CACHE; OS_CACHE_UNCONTROLLED",
        "runs": [],
    }
    with Session() as db:
        db.add(Organization(id="benchmark", name="Benchmark"))
        db.flush()
        user = User(
            id="benchmark",
            organization_id="benchmark",
            email="benchmark@example.invalid",
            password_hash="unused",
            role="ORG_OWNER",
        )
        repo = Repository(
            id="benchmark",
            organization_id="benchmark",
            name="Static fixture",
            system="Benchmark",
            component="Component",
            owner="Benchmark",
            provider="LOCAL",
        )
        db.add_all([user, repo])
        db.flush()
        db.add(Grant(user_id=user.id,repository_id=repo.id))
        db.commit()
        inventory = capture(db, user.organization_id, repo, ((p, t.encode()) for p, t in sources.items()))
        db.commit()
        files = RepositoryFiles(db, user.organization_id, repo.id, inventory.id)
        base = None
        sql = {"queries": 0, "seconds": 0.0, "flushes": 0, "max_flush_rows": 0}

        @event.listens_for(engine, "before_cursor_execute")
        def before_cursor(_c, _cursor, _s, _p, context, _m):
            context.benchmark_started = time.perf_counter()

        @event.listens_for(engine, "after_cursor_execute")
        def after_cursor(_c, _cursor, _s, _p, context, _m):
            sql["queries"] += 1
            sql["seconds"] += time.perf_counter() - context.benchmark_started

        @event.listens_for(db, "before_flush")
        def before_flush(session, *_):
            sql["flushes"] += 1
            sql["max_flush_rows"] = max(sql["max_flush_rows"], len(session.new) + len(session.dirty))

        for number, mode in enumerate(("cold", "warm", "one_file_change")):
            if mode == "one_file_change":
                changed_path = next(iter(sources))
                sources[changed_path] += (
                    "\n/* benchmark-only source comment */\n"
                    if changed_path.endswith((".java", ".ts", ".tsx", ".js"))
                    else "\n# benchmark-only source comment\n"
                )
                inventory = capture(db, user.organization_id, repo, ((p, t.encode()) for p, t in sources.items()))
                db.commit()
                files = RepositoryFiles(db, user.organization_id, repo.id, inventory.id)
            for k in sql:
                sql[k] = 0
            profiler = cProfile.Profile()
            with Resources() as resources:
                if args.profile:
                    profiler.enable()
                snapshot, job = execute_analysis(
                    db,
                    user,
                    repo,
                    files,
                    git_commit=str(number + 1) * 40,
                    base_id=base.id if mode == "one_file_change" and base else None,
                )
                if args.profile:
                    profiler.disable()
            base = snapshot
            run = {
                "mode": mode,
                **resources.result,
                "database": dict(sql),
                "state": job.data["state"],
                "job_duration_ms": job.data["duration_ms"],
                "performance": job.data.get("performance"),
                "coverage": snapshot.data["analysis_coverage"]["summary"],
                "source_storage": snapshot.data.get("source_storage"),
                "findings": len(snapshot.data["findings"]),
                "graph_nodes": db.scalar(
                    select(func.count())
                    .select_from(Record)
                    .where(Record.kind == "graph_node", Record.data["scope"]["snapshot_id"].as_string() == snapshot.id)
                ),
            }
            receipt["runs"].append(run)
            if args.profile:
                profiler.dump_stats(str(target / (mode + ".pstats")))
                stats = pstats.Stats(profiler)
                run["profile_top"] = [
                    {
                        "function": Path(f[0]).name + ":" + str(f[1]) + ":" + f[2],
                        "calls": v[1],
                        "self_seconds": round(v[2], 6),
                        "cumulative_seconds": round(v[3], 6),
                    }
                    for f, v in sorted(stats.stats.items(), key=lambda item: item[1][3], reverse=True)[:45]
                ]
            (target / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            print(
                json.dumps({k: v for k, v in run.items() if k not in ("performance", "source_storage", "profile_top")}),
                flush=True,
            )


if __name__ == "__main__":
    main()
