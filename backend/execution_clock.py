"""Elapsed working-state time for benchmark reporting; ordinary wall time is also retained."""

import ctypes
import os
import time

if os.name == "nt":
    _kernel = ctypes.WinDLL("kernelbase", use_last_error=True)
    _unbiased = _kernel.QueryUnbiasedInterruptTimePrecise
    _unbiased.argtypes = [ctypes.POINTER(ctypes.c_uint64)]
    _unbiased.restype = None


def active_time():
    if os.name == "nt":
        value = ctypes.c_uint64()
        _unbiased(ctypes.byref(value))
        return value.value / 10_000_000
    return time.monotonic()
