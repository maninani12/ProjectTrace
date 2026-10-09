"""Privacy-safe, actionable intake failures shared by APIs and worker records."""


class IntakeError(ValueError):
    def __init__(self, code, message, *, budget=None, actual=None, maximum=None, remediation=None):
        self.code, self.budget, self.actual, self.maximum = code, budget, actual, maximum
        self.remediation = remediation or "Correct the source archive and import a new snapshot."
        if budget is not None:
            message += f" {budget}: actual {actual}; maximum {maximum}."
        self.message = message + " " + self.remediation
        super().__init__(self.message)

    def detail(self):
        result = {"code": self.code, "message": self.message, "remediation": self.remediation}
        if self.budget is not None:
            result.update(budget=self.budget, actual=self.actual, maximum=self.maximum)
        return result
