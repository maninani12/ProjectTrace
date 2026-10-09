"""Safe Windows development startup, verified readiness and graceful stop."""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/local-runtime.json"
STOP = ROOT / "data/local-api.stop"


def load_config(path, environment):
    result = dict(environment)
    if path:
        with Path(path).open("rb") as stream:
            raw = stream.read(32769)
        if len(raw) > 32768:
            raise ValueError("Local config exceeds 32,768 bytes.")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Local config must be a JSON object of environment names and strings.")
        allowed = {"APP_ENV", "JOB_MODE", "CORS_ORIGINS", "SOURCE_BLOB_DIR", "SOURCE_UPLOAD_DIR", "ANALYSIS_KEY_FILE", "OSV_ENABLED", "REDIS_URL"}
        for key, setting in value.items():
            secret = re.fullmatch(r"(?:SCM_[A-Z0-9_]{1,80}|DATABASE_URL|REDIS_URL|ANALYSIS_INPUT_KEY|GITHUB_PRIVATE_KEY|GITHUB_WEBHOOK_SECRET)_FILE", key)
            quota = re.fullmatch(r"(?:REPOSITORY_MAX_(?:FILES|BYTES|ARCHIVE_BYTES)|REPOSITORY_ANALYSIS_SECONDS|QUEUE_[A-Z_]+)", key)
            if not isinstance(setting, str) or (key not in allowed and not secret and not quota):
                raise ValueError("Unsupported local config name/value. Use operator-owned *_FILE references for secrets.")
            if secret and (not Path(setting).is_absolute() or not Path(setting).is_file()):
                raise ValueError("Secret-file references must be existing absolute file paths.")
            if key == "REDIS_URL" and setting != "redis://127.0.0.1:6379/0":
                raise ValueError("Local config accepts only the noncredentialed loopback Redis URL; use *_FILE for deployed brokers.")
            result[key] = setting
    if result.get("APP_ENV") == "production":
        raise ValueError("Local runtime is unavailable in production; use deployment tooling.")
    result.setdefault("APP_ENV", "demo")
    result.setdefault("JOB_MODE", "local")
    if result["JOB_MODE"] not in {"local", "celery"}:
        raise ValueError("Managed startup supports JOB_MODE=local or celery.")
    return result


def hidden(arguments, **kwargs):
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(arguments, **kwargs)


def probe(url):
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.status == 200
    except OSError:
        return False


def occupied(port):
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def identity(pid):
    if os.name != "nt":
        raise ValueError("This controller supports Windows; use the documented POSIX foreground commands.")
    command = f"Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}' | Select-Object ProcessId,CreationDate,CommandLine | ConvertTo-Json -Compress"
    reply = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
    return json.loads(reply.stdout) if reply.returncode == 0 and reply.stdout.strip() else None


def verified(entry):
    actual = identity(entry["pid"])
    return actual is not None and actual == entry["identity"]


def stop():
    if not STATE.exists():
        raise ValueError("No managed runtime is recorded. Unmanaged listeners were retained.")
    state = json.loads(STATE.read_text())
    api = state["api"]
    if verified(api):
        command = api["identity"]["CommandLine"].lower()
        if "local_api.py" not in command or str(ROOT).lower() not in command:
            raise ValueError("Recorded API identity is outside this project; nothing stopped.")
        STOP.touch()
        print("Graceful stop requested. Current analysis may finish; queued inputs are retained.", flush=True)
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline and verified(api):
            time.sleep(2)
        if verified(api):
            raise ValueError("API is still draining and was retained. Inspect job status and rerun stop after completion.")
    ui = state["ui"]
    if verified(ui):
        expected = str(ROOT / "frontend/node_modules/vite/bin/vite.js").lower().replace("\\", "/")
        if expected not in ui["identity"]["CommandLine"].lower().replace("\\", "/"):
            raise ValueError("Recorded UI identity is outside this project; it was retained.")
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", f"Stop-Process -Id {int(ui['pid'])} -ErrorAction Stop"], check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    STATE.unlink(missing_ok=True)
    STOP.unlink(missing_ok=True)
    print("Managed API/UI stopped; database, accounts, keys, history and optional workers retained.")


def start(args):
    default_config = ROOT / "data/local-settings.json"
    environment = load_config(args.config or (default_config if default_config.is_file() else None), os.environ)
    if args.full_development:
        environment["JOB_MODE"] = "celery"
        environment.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
    if occupied(8011) or occupied(5181):
        if probe("http://127.0.0.1:8011/ready") and probe("http://127.0.0.1:5181/api/auth/options"):
            print("Existing API and UI are ready: http://127.0.0.1:5181. Processes/configuration retained.")
            return
        raise ValueError("Port 8011 or 5181 is occupied, but API/UI readiness failed. Listeners were retained; inspect project logs.")
    python = ROOT / ".venv/Scripts/python.exe"
    vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
    node = shutil.which("node.exe")
    if not python.is_file() or not vite.is_file() or not node:
        raise ValueError("Project Python, UI dependencies or Node are missing. Follow README setup; nothing is installed automatically.")
    (ROOT / "data").mkdir(exist_ok=True)
    subprocess.run([str(python), "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=environment, check=True)
    if args.full_development:
        command = [str(python), str(ROOT / "scripts/dev_workers.py"), "--with-beat"]
        if args.docker_redis:
            command.append("--docker-redis")
        subprocess.run(command, cwd=ROOT, env=environment, check=True)
    elif environment["JOB_MODE"] == "celery":
        raise ValueError("Celery mode requires a worker; use -FullDevelopment for optional worker startup.")
    # Demo seeding is separate. Startup never resets or seeds existing accounts.
    with (ROOT / "data/api.log").open("ab") as out, (ROOT / "data/api-error.log").open("ab") as err:
        api = hidden([str(python), str(ROOT / "scripts/local_api.py")], cwd=ROOT, env=environment, stdout=out, stderr=err)
    with (ROOT / "data/ui.log").open("ab") as out, (ROOT / "data/ui-error.log").open("ab") as err:
        ui = hidden([node, str(vite), "--host", "127.0.0.1", "--port", "5181", "--strictPort"], cwd=ROOT / "frontend", env=environment, stdout=out, stderr=err)
    state = {role: {"pid": child.pid, "identity": identity(child.pid)} for role, child in (("api", api), ("ui", ui))}
    STATE.write_text(json.dumps(state, indent=2))
    for _ in range(45):
        if api.poll() is not None or ui.poll() is not None:
            raise ValueError("A process exited during startup. Inspect data logs; stop.ps1 can stop the recorded runtime safely.")
        if probe("http://127.0.0.1:8011/ready") and probe("http://127.0.0.1:5181/api/auth/options"):
            print("API database and UI auth proxy ready: http://127.0.0.1:5181 (mode " + environment["JOB_MODE"] + ").")
            return
        time.sleep(1)
    raise ValueError("Readiness timed out. Inspect data logs; no startup success was reported.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop"])
    parser.add_argument("--config")
    parser.add_argument("--full-development", action="store_true")
    parser.add_argument("--docker-redis", action="store_true")
    args = parser.parse_args()
    if args.docker_redis and not args.full_development:
        raise ValueError("Docker Redis requires explicit FullDevelopment.")
    stop() if args.action == "stop" else start(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error) if isinstance(error, ValueError) else f"Local runtime failed ({type(error).__name__}); inspect project logs.", file=sys.stderr)
        sys.exit(1)
