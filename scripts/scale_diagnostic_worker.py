"""Trusted child bootstrap timing for the explicitly opted-in IaC probe."""
import json
import runpy
import sys
import time


def main():
    started = time.perf_counter_ns()
    script, operation = sys.argv[1:]
    if operation not in ("iac", "iac_without_hcl"):
        raise ValueError("Unsupported diagnostic worker operation")
    sys.argv = [script, operation]
    worker = runpy.run_path(script, run_name="scale_diagnostic_worker")
    worker_main = worker["main"]
    state = worker_main.__globals__
    prepare = state["prepare"]
    timings = {}

    def measured_prepare(selected):
        begin = time.perf_counter_ns()
        prepared = prepare(selected)
        timings.update(prepare_ns=time.perf_counter_ns()-begin, grammar_prepared=callable(prepared[-1]))
        sandbox = prepared[1]
        install = sandbox.install

        def measured_install(paths):
            begin = time.perf_counter_ns()
            result = install(paths)
            timings["containment_ns"] = time.perf_counter_ns() - begin
            return result
        sandbox.install = measured_install
        return prepared

    class ProofJson:
        emitted = False

        def dumps(self, value, **kwargs):
            if not self.emitted and isinstance(value, dict) and value.get("enforced") is True:
                self.emitted = True
                value = {**value, "scale_diagnostic": {**timings, "attestation_ns": time.perf_counter_ns()-started}}
            return json.dumps(value, **kwargs)

        def __getattr__(self, name):
            return getattr(json, name)

    state["prepare"], state["json"] = measured_prepare, ProofJson()
    worker_main()


if __name__ == "__main__":
    main()
