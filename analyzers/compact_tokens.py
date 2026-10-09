"""Lossless in-memory token representation; durable parser artifacts are unchanged."""

from array import array
from collections.abc import Sequence


class CompactTokens(Sequence):
    def __init__(self, tokens):
        self.values = tuple(t["value"] for t in tokens)
        self.lines = array("I", (t["line"] for t in tokens))

    def __len__(self):
        return len(self.values)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [{"value": self.values[i], "line": self.lines[i]} for i in range(*index.indices(len(self)))]
        return {"value": self.values[index], "line": self.lines[index]}
