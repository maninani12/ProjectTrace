# SCALE-001 quality inventory attribution gate

November 8, 2026. Commercial V1 **DEVELOPMENT IN PROGRESS**. SCALE-001 **NOT QUALIFIED**.

At `36974d520467ad7a50df2818440a029e58c5fd17`, validation 42429016512 passed all four jobs. SCALE-001 run 42429016555 failed baseline with a verified 768,000,000-byte OOM and candidate with `ANALYSIS_TIME_BUDGET` in VERIFYING. Both databases passed integrity and foreign-key checks. Both published zero generations and pointers. Candidate FINAL_IDENTITY, checkpoint admission and warm execution were unreached. [Validation](https://github.com/maninani12/ProjectTrace/actions/runs/42429016512) Â· [SCALE-001](https://github.com/maninani12/ProjectTrace/actions/runs/42429016555)

One `QUALITY_INVENTORY` call took 121.962 wall seconds and 122.623 cgroup CPU seconds. It recorded zero device-read bytes, 7,179 reclaim scans and 108 memory-ceiling events. The deadline fired in the later `QUALITY_RULES` signal iteration. That interval through parent unwind recorded 362,717,184 device-read bytes and 89,023 scans. Exact full-run worker starts, source/query attribution and reclaim cost are unknown.

Matched cold and warm 24- and 128-file OpenMetadata trials attributed over 99% of bounded inventory wall time to isolated worker calls. A separate attested companion measured 301â€“306 ms of trusted preparation and 0.825â€“2.228 ms of classification dispatch per measured batch median. Inventory issued zero source reads, application SQL and encrypted spill reads. The later rules pass spent most of its bounded wall time reading encrypted observations. WSL/Docker pressure was **NOT EQUIVALENT** to Azure.

The reference and counted trials preserved output, evidence ordering and publication identities. Linux development and required selections passed 208 and 146 tests, respectively. Both SEC-002 probes passed on the unchanged 199-file image. This is an evidence-only qualification. Runtime, workflow and resource policies are unchanged.

Another full run is unwarranted at this milestone. The next bounded investigation is a narrower trusted bootstrap for metadata-only lexical classification with ordered-result equivalence and the same fail-closed enforcement and denial checks. The complete release gates still apply. [Sanitized receipt](evidence/SCALE001_QUALITY_INVENTORY_ATTRIBUTION_20261108.json) Â· [Diagnostic activation gate](SCALE001_DIAGNOSTIC_ACTIVATION_GATE_20261108.md) Â· [Integrated qualification gate](SCALE001_INTEGRATED_QUALIFICATION_GATE.md)
