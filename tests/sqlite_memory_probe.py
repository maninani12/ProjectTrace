"""Diagnostic counters from the already loaded Windows SQLite DLL only."""
import ctypes
import os
import sqlite3


class SQLiteMemory:
    def __init__(self):
        self.library = None
        if os.name != 'nt':
            return
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        kernel.GetModuleHandleW.restype = ctypes.c_void_p
        handle = kernel.GetModuleHandleW('sqlite3.dll')
        if not handle:
            return
        library = ctypes.CDLL(None, handle=handle)
        library.sqlite3_libversion.restype = ctypes.c_char_p
        if library.sqlite3_libversion().decode() != sqlite3.sqlite_version:
            return
        library.sqlite3_memory_used.argtypes = []
        library.sqlite3_memory_used.restype = ctypes.c_longlong
        library.sqlite3_memory_highwater.argtypes = [ctypes.c_int]
        library.sqlite3_memory_highwater.restype = ctypes.c_longlong
        self.library = library

    def begin(self):
        if self.library is None:
            return None
        self.library.sqlite3_memory_highwater(1)
        return self.library.sqlite3_memory_used()

    def end(self, before):
        if self.library is None:
            return {'available': False}
        return {'available': True, 'sqlite_version': sqlite3.sqlite_version,
            'before_malloc_bytes': before, 'after_malloc_bytes': self.library.sqlite3_memory_used(),
            'peak_malloc_bytes': self.library.sqlite3_memory_highwater(0)}
