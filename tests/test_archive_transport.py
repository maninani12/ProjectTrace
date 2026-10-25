"""Portable owned IPC regressions; these do not certify Linux containment."""

import io
import json
import os
import signal
import struct
import subprocess
import sys
from types import SimpleNamespace

import pytest

from analyzers import sandbox
from analyzers.archive_transport import CHUNK, RemoteArchive, Wire


def test_remote_archive_reads_in_bounded_ranges_without_keys_or_paths(monkeypatch):
    data = b"a" * CHUNK + b"tail"
    stdin = io.BytesIO(struct.pack("!I", CHUNK) + data[:CHUNK] + struct.pack("!I", 4) + data[CHUNK:])
    stdout = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=stdin))
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=stdout))
    remote = RemoteArchive(len(data))
    assert remote.read() == data
    assert remote.tell() == len(data) and remote.read() == b""
    requests = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert requests == [{"read": [0, CHUNK]}, {"read": [CHUNK, 4]}]
    assert remote.seek(-4, 2) == CHUNK
    with pytest.raises(ValueError):
        remote.seek(-1)


@pytest.mark.skipif(os.name != "posix", reason="Linux duplex transport; no Windows isolation equivalence")
@pytest.mark.parametrize("fault,code", [("stderr", "ARCHIVE_HELPER_TIMEOUT"), ("packet", "ARCHIVE_PACKET_BUDGET")])
def test_wire_bounds_actual_stderr_flood_and_unterminated_output(fault, code):
    script = "import os\nwhile True: os.write(2,b'x'*65536)" if fault == "stderr" else "import os; os.write(1,b'x'*2000000)"
    process = subprocess.Popen([sys.executable, "-c", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        wire = Wire(process, 0.3 if fault == "stderr" else 3)
        with pytest.raises(sandbox.SandboxFailure, match=code):
            wire.line()
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        for pipe in (process.stdin, process.stdout, process.stderr):
            pipe.close()
