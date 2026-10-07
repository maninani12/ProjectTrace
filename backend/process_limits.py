"""Resource ceilings for owned processes; these are not network or filesystem sandboxes."""

import ctypes
import os

_JOB_HANDLES = []


def windows_job(memory_bytes, cpu_seconds, *, process_handle=None):
    if os.name != "nt":
        raise RuntimeError("Windows Job Objects are unavailable on this platform.")
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_int64),
            ("job_time", ctypes.c_int64),
            ("flags", wintypes.DWORD),
            ("minimum_working_set", ctypes.c_size_t),
            ("maximum_working_set", ctypes.c_size_t),
            ("active_process_limit", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority", wintypes.DWORD),
            ("scheduling", wintypes.DWORD),
        ]

    class IOCounters(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_uint64)
            for name in [
                "read_operations",
                "write_operations",
                "other_operations",
                "read_bytes",
                "write_bytes",
                "other_bytes",
            ]
        ]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("basic", Basic),
            ("io", IOCounters),
            ("process_memory", ctypes.c_size_t),
            ("job_memory", ctypes.c_size_t),
            ("peak_process_memory", ctypes.c_size_t),
            ("peak_job_memory", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    kernel.QueryInformationJobObject.restype = wintypes.BOOL
    if not 64_000_000 <= memory_bytes <= 8_000_000_000 or not 1 <= cpu_seconds <= 7200:
        raise ValueError("Owned process resource ceilings are outside their supported bounds.")
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise OSError("Windows resource job creation failed.")
    settings = Extended()
    settings.basic.flags = 0x100 | 0x200 | 0x2
    settings.basic.process_time = int(cpu_seconds * 10_000_000)
    settings.process_memory = memory_bytes
    settings.job_memory = memory_bytes
    if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(settings), ctypes.sizeof(settings)):
        kernel.CloseHandle(handle)
        raise OSError("Windows resource job configuration failed.")
    selected = process_handle if process_handle is not None else kernel.GetCurrentProcess()
    if not kernel.AssignProcessToJobObject(handle, selected):
        kernel.CloseHandle(handle)
        raise OSError("Windows resource job assignment failed.")
    checked = Extended()
    if not kernel.QueryInformationJobObject(handle, 9, ctypes.byref(checked), ctypes.sizeof(checked), None):
        raise OSError("Windows resource job verification failed.")
    # Keep self-assigned limits alive until process exit. This never targets the parent app.
    _JOB_HANDLES.append(handle)
    return {
        "kind": "WINDOWS_JOB_OBJECT",
        "memory_commit_limit_bytes": checked.process_memory,
        "job_memory_limit_bytes": checked.job_memory,
        "cpu_user_seconds_per_process": checked.basic.process_time / 10_000_000,
        "network_isolation": "NOT_PROVIDED",
        "filesystem_isolation": "NOT_PROVIDED",
    }


def self_limits(memory_bytes, cpu_seconds):
    if os.name == "nt":
        return windows_job(memory_bytes, cpu_seconds)
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    return {
        "kind": "POSIX_RLIMIT",
        "address_space_limit_bytes": memory_bytes,
        "cpu_seconds": cpu_seconds,
        "network_isolation": "NOT_PROVIDED",
        "filesystem_isolation": "NOT_PROVIDED",
    }
