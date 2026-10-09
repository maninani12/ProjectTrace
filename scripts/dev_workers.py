"""Explicit local development worker bootstrap. Imported repositories are never run."""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate_local(environment):
    if environment.get("APP_ENV", "demo") == "production":
        raise ValueError("Development worker startup is unavailable in production.")
    if environment.get("REDIS_URL", "redis://127.0.0.1:6379/0") != "redis://127.0.0.1:6379/0":
        raise ValueError("Development bootstrap requires local Redis on 127.0.0.1:6379/0; use deployment tooling for other brokers.")


def missing_credentials(metadata, environment):
    required = set()
    for data in metadata:
        if not data.get("enabled"):
            continue
        for key in ("private_key_ref", "webhook_secret_ref", "ca_bundle_ref"):
            reference = data.get(key)
            if not reference and key == "ca_bundle_ref":
                continue
            if not isinstance(reference, str) or not re.fullmatch(r"ENV:SCM_[A-Z0-9_]{1,80}", reference):
                raise ValueError("Configured SCM credential reference is invalid.")
            required.add(reference[4:])
    if environment.get("GITHUB_APP_ID"):
        required.update({"GITHUB_PRIVATE_KEY", "GITHUB_WEBHOOK_SECRET", "GITHUB_INSTALLATION_ID"})
    return sorted(name for name in required if not environment.get(name))


def validate_redis_container(data):
    bindings = data.get("HostConfig", {}).get("PortBindings", {}).get("6379/tcp", [])
    if bindings != [{"HostIp": "127.0.0.1", "HostPort": "6379"}]:
        raise ValueError("Existing projecttrace-redis must bind only 127.0.0.1:6379; container configuration was not changed.")
    if data.get("Config", {}).get("Image") != "redis:7-alpine":
        raise ValueError("Existing projecttrace-redis uses another image; review it before reuse.")


def run(arguments, **options):
    return subprocess.run(arguments, capture_output=True, text=True, timeout=options.pop("timeout", 15), **options)


def hidden_launch(arguments, stdout, stderr, environment):
    options = {}
    if os.name == "nt":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        options.update(startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
    return subprocess.Popen(arguments, cwd=ROOT, env=environment, stdout=stdout, stderr=stderr, **options)


def local_process_running(role):
    if role not in {"worker", "beat"}:
        raise ValueError("Unknown development process role.")
    if os.name != "nt":
        return (ROOT / ("data/celerybeat.pid" if role == "beat" else "data/celery-worker.pid")).exists()
    project_python = str(ROOT / ".venv/Scripts/python.exe").replace("'", "''")
    command = "$taskPython='" + project_python + "'; [bool](Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $taskPython -and $_.CommandLine -match 'workers\\.tasks\\s+" + role + "\\b' })"
    checked = run(["powershell.exe", "-NoProfile", "-Command", command])
    if checked.returncode:
        raise ValueError("Unable to verify existing local processes; no additional process was started.")
    return checked.stdout.strip().lower() == "true"


def ensure_no_existing_worker(app):
    # A busy Windows solo worker cannot answer ping; inspect this project's
    # launcher first so lack of a control reply cannot create a duplicate.
    if local_process_running("worker") or app.control.ping(timeout=3):
        raise ValueError("A worker already exists for this project/broker. Keep it, or stop only its verified ProjectTrace processes before restarting to load code/configuration changes.")


def ensure_redis(allow_docker):
    from redis import Redis

    redis = Redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=2, socket_timeout=2)
    try:
        if redis.ping():
            print("Local Redis: PONG (existing service)")
            return
    except Exception:
        pass
    if not allow_docker:
        raise ValueError("Local Redis is unavailable. Start your existing local Redis or opt into --docker-redis.")
    docker = shutil.which("docker") or str(Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"))
    if not Path(docker).is_file():
        raise ValueError("Docker is unavailable. Install/start local Redis or Docker Desktop, then retry.")
    environment = os.environ.copy()
    environment["PATH"] = str(Path(docker).parent) + os.pathsep + environment.get("PATH", "")
    if run([docker, "info", "--format", "{{.ServerVersion}}"], env=environment).returncode:
        desktop = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")
        if not desktop.is_file():
            raise ValueError("Docker daemon is unavailable; start your configured engine and retry.")
        hidden_launch([str(desktop)], subprocess.DEVNULL, subprocess.DEVNULL, environment)
        for _ in range(15):
            if run([docker, "info", "--format", "{{.ServerVersion}}"], env=environment).returncode == 0:
                break
            time.sleep(2)
        else:
            raise ValueError("Docker Desktop did not become ready. Complete required Windows/WSL or Docker setup; no host security settings were changed.")
    inspected = run([docker, "inspect", "projecttrace-redis"], env=environment)
    if inspected.returncode == 0:
        data = json.loads(inspected.stdout)[0]
        validate_redis_container(data)
        command = [docker, "start", "projecttrace-redis"]
    else:
        command = [docker, "run", "-d", "--name", "projecttrace-redis", "--restart", "unless-stopped", "-p", "127.0.0.1:6379:6379", "redis:7-alpine"]
    if run(command, env=environment, timeout=120).returncode:
        raise ValueError("Redis container startup failed; inspect Docker Desktop and its local container status.")
    for _ in range(10):
        try:
            if redis.ping():
                print("Local Redis: PONG (projecttrace-redis)")
                return
        except Exception:
            time.sleep(1)
    raise ValueError("Redis did not answer PING on the local configured port.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker-redis", action="store_true")
    parser.add_argument("--with-beat", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--require-scm", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    validate_local(os.environ)
    os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
    os.environ["JOB_MODE"] = "celery"
    from sqlalchemy import select

    from backend.db import Record, Session
    from workers.tasks import celery

    with Session() as db:
        metadata = [connection.data for connection in db.scalars(select(Record).where(Record.kind == "scm_connection"))]
    missing = missing_credentials(metadata, os.environ)
    if missing:
        message = "SCM credential references unavailable: " + ", ".join(missing) + ". Use operator-owned *_FILE references for private SCM/webhooks. ZIP/public snapshots remain independent."
        if args.require_scm:
            raise ValueError(message)
        print(message)
    if args.check_only:
        print("Development configuration and credential-reference presence checks passed; nothing started.")
        return
    ensure_redis(args.docker_redis)
    ensure_no_existing_worker(celery)
    environment = os.environ.copy()
    logs = ROOT / "data"
    logs.mkdir(exist_ok=True)
    node = "projecttrace-development@" + socket.gethostname()
    worker_logs = [logs / "worker.log", logs / "worker-error.log"]
    offsets = {path: path.stat().st_size if path.exists() else 0 for path in worker_logs}
    with (logs / "worker.log").open("ab") as stdout, (logs / "worker-error.log").open("ab") as stderr:
        worker = hidden_launch([sys.executable, "-m", "celery", "-A", "workers.tasks", "worker", "--pool=solo", "--loglevel=INFO", "--queues=native,large,scm,advisory,celery", "--hostname", node, "--pidfile", str(logs / "celery-worker.pid")], stdout, stderr, environment)
    for _ in range(30):
        if worker.poll() is not None:
            raise ValueError("Worker exited during startup; inspect data/worker-error.log.")
        ready = False
        for path in worker_logs:
            with path.open("rb") as stream:
                stream.seek(offsets[path])
                ready |= (node + " ready.").encode() in stream.read(256000)
        # Solo workers cannot answer control ping while handling a long task.
        # A fresh ready banner from this launch avoids killing a busy valid worker.
        if ready:
            print(f"Worker ready; launcher PID {worker.pid}; queues native,large,scm,advisory,celery.")
            break
        time.sleep(1)
    else:
        if os.name == "nt":
            run(["taskkill", "/PID", str(worker.pid), "/T", "/F"])
        else:
            worker.terminate()
        raise ValueError("Worker did not become ready; its new launcher was stopped. Inspect local worker logs.")
    if args.with_beat:
        if local_process_running("beat"):
            print("Existing ProjectTrace Beat retained; no duplicate scheduler started.")
        else:
            with (logs / "beat.log").open("ab") as stdout, (logs / "beat-error.log").open("ab") as stderr:
                beat = hidden_launch([sys.executable, "-m", "celery", "-A", "workers.tasks", "beat", "--loglevel=INFO", "--schedule", str(logs / "celerybeat-schedule"), "--pidfile", str(logs / "celerybeat.pid")], stdout, stderr, environment)
            print(f"Beat launcher PID {beat.pid}; periodic queued-job recovery enabled.")
    celery.send_task("projecttrace.recover_jobs")
    print("Existing queued-job recovery requested. Beat is not required for this immediate recovery.")


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print(f"Development startup failed ({type(error).__name__}); no raw exception or credentials displayed.", file=sys.stderr)
        sys.exit(1)
