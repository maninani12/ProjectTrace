"""Host-owned Docker cgroup v2 enforcement and durable qualification diagnostics."""
import argparse
import json
import os
import subprocess
import threading
import time
from pathlib import Path

LIMIT = 768_000_000


def docker(*args, **kwargs):
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True, **kwargs).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()
    if os.getuid() == 0:
        parser.error("Run the host harness as an ordinary runner user.")
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Output must be a fresh directory.")
    output.mkdir(parents=True, exist_ok=True)
    artifact = output / "container-envelope.json"
    command = ["create", "--memory", str(LIMIT), "--memory-swap", str(LIMIT), "--cpus", "2", "--pids-limit", "64",
               "--cgroupns", "private", "--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--user", f"{os.getuid()}:{os.getgid()}", "--mount", f"type=bind,src={args.archive.resolve()},dst=/input.zip,readonly",
               "--mount", f"type=bind,src={output},dst=/evidence", "-e", "PROJECTTRACE_PARSER_ISOLATION=required",
               args.image, "python", "-m", "scripts.qualify_scale_workload", "--archive", "/input.zip", "--output", "/evidence"]
    if args.manifest_only:
        command.append("--manifest-only")
    identity = docker(*command)
    evidence = {"memory_limit_bytes": LIMIT, "swap_limit_bytes": 0, "container": identity,
                "all_descendants_in_container_cgroup": True, "network": "none", "sec002": "required",
                "postgres_redis": "Outside this SQLite qualification container; separate acceptance jobs",
                "docker_server": json.loads(docker("version", "--format", "{{json .Server}}"))}
    stop = threading.Event()
    thread = None
    try:
        docker("start", identity)
        info = json.loads(docker("inspect", identity))[0]
        config = info["HostConfig"]
        if config["Memory"] != LIMIT or config["MemorySwap"] != LIMIT or config["CgroupnsMode"] != "private":
            raise RuntimeError("Docker resource envelope differs from requested qualification.")
        evidence["configured"] = {k: config[k] for k in ("Memory", "MemorySwap", "PidsLimit", "CgroupnsMode", "NetworkMode")}
        pid = info["State"]["Pid"]
        hierarchy = Path(f"/proc/{pid}/cgroup").read_text().strip().split("0::", 1)[1]
        root = Path("/sys/fs/cgroup") / hierarchy.lstrip("/")
        if not (root / "memory.max").is_file():
            raise RuntimeError("Host cannot observe the actual container cgroup.")
        if int((root / "memory.max").read_text()) != LIMIT or int((root / "memory.swap.max").read_text()) != 0:
            raise RuntimeError("Kernel did not enforce the requested memory/swap limits.")
        evidence["kernel_enforcement_verified"] = True
        artifact.write_text(json.dumps(evidence, indent=2))

        def sample():
            with (output / "kernel-cgroup.jsonl").open("w") as stream:
                while not stop.is_set():
                    try:
                        row = {name: (root / name).read_text().strip() for name in
                               ("memory.current", "memory.peak", "memory.events", "memory.swap.current", "cgroup.procs")}
                        row["monotonic"] = time.monotonic()
                        stream.write(json.dumps(row) + "\n")
                        stream.flush()
                        evidence["last_kernel_sample"] = row
                    except OSError:
                        break
                    stop.wait(0.1)
        thread = threading.Thread(target=sample, daemon=True)
        thread.start()
        try:
            exit_status = int(docker("wait", identity, timeout=2400))
        except subprocess.TimeoutExpired:
            evidence["timeout_seconds"] = 2400
            docker("stop", "--time", "5", identity)
            exit_status = int(docker("wait", identity, timeout=30))
        state = json.loads(docker("inspect", identity))[0]["State"]
        evidence.update(exit_status=exit_status, oom_killed=state["OOMKilled"], container_error=state["Error"])
        if exit_status:
            raise RuntimeError("Resource-constrained qualification did not pass; retained evidence records the failure.")
    finally:
        stop.set()
        if thread:
            thread.join(timeout=5)
        artifact.write_text(json.dumps(evidence, indent=2))
        # Remove only the disposable owned container; never any source/db volume.
        subprocess.run(["docker", "stop", "--time", "1", identity], capture_output=True)
        subprocess.run(["docker", "rm", identity], capture_output=True)


if __name__ == "__main__":
    main()
