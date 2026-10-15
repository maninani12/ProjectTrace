"""Canonical operator-owned storage paths, including Windows extended-length paths."""
import os
from pathlib import Path


def storage_path(value):
    path = Path(value).resolve()
    raw = str(path)
    if os.name == "nt" and not raw.startswith("\\\\?\\"):
        raw = "\\\\?\\UNC\\" + raw[2:] if raw.startswith("\\\\") else "\\\\?\\" + raw
        path = Path(raw)
    return path
