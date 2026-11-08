# SCALE-001 native-partition qualification supplement

November 7, 2026 · Commercial V1 **DEVELOPMENT IN PROGRESS** · SCALE-001 **NOT QUALIFIED**

This supplement records the bounded native-partition investigation following the [integrated SCALE-001 gate](SCALE001_INTEGRATED_QUALIFICATION_GATE.md) and its OpenAPI deadline attribution. The earlier gate and its receipt were preserved byte-for-byte.

At ProjectTrace commit `200905bb4b7fcf8ab5e42c07c9f7f6c2c280a617`, the baseline in run 42373565217 exited 137 with verified OOM at 768,000,000 bytes and zero swap. The candidate exited 1 on ANALYSIS_TIME_BUDGET after an OpenAPI helper returned. The preceding native partition spans totaled 1,598.843 seconds. Neither job published a generation or pointer. The candidate did not reach FINAL_IDENTITY or checkpoint admission. [Retained CI](https://github.com/maninani12/ProjectTrace/actions/runs/42373565217)

Two matched SQLite slices from pinned OpenMetadata `b1fab2bc21c63335dead4daaaa28194c9878e9bf` showed an unnecessary HCL grammar build in non-Terraform IaC workers. The correction routes those batches through a fixed, contained worker operation and rejects misrouted Terraform before any file packet. On an authentic six-file YAML/Dockerfile companion batch, median helper round trip went from 1.055 to 0.187 seconds with matching ordered packets. The 128-file cold native parse median went from 2.946 to 2.082 seconds. Ordered findings, claims, evidence and ParserArtifact digests matched in the bounded jobs. The slices did not reproduce the full runner's memory reclaim. Full-scale gain and publication remain unverified.

Linux development passed 143 tests. The required-mode selection passed 133 with one development-only test deselected after its parser-signature mismatch reproduced on the original runtime. Both SEC-002 probes exited 0 on the distinct 196-file candidate image. The next bounded measurement is launch frequency by IaC route and retained packet admission time by type under runner-equivalent reclaim. [Sanitized qualification receipt](evidence/SCALE001_NATIVE_PARTITION_ATTRIBUTION_20261107.json)
