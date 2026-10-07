"""Text source with bounded, non-executable ZIP intake diagnostics."""


class SourceFiles(dict):
    def __init__(self, values=(), *, intake=()):
        super().__init__(values)
        self.intake = list(intake)
