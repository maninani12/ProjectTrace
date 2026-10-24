# SEC-002 parser containment: implementation and acceptance

Status: **implementation under qualification; overall SEC-002 remains OPEN**. Do not infer security from a build or resource-limit flag. Current-head PR #3 checks are authoritative; prior green PR #2 run 40126311475 proves the preserved baseline only.

## Threat model and reviewed call graph

Assume attacker-controlled repository text exploits a syntax/parser dependency and obtains arbitrary code execution in that parser process. The application coordinator, immutable installed ProjectTrace/runtime files, Linux kernel/LSMs, libseccomp, and bounded IPC decoder remain trusted. Repository scripts, package installers, templates and builds are never executed.

| Boundary | Input / previous exposure | New required-mode boundary / limit |
|---|---|---|
| JS/TS/TSX/Java | `engine.native_observations` → `languages.analyze_languages` → Tree-sitter; old child could access host filesystem/network | Attested owned worker, 512 MB / 25 CPU seconds / 30 wall seconds; 512 KB/file, original 1,000-file/10 MB native batch, 10,000 metrics and 16 MB output caps retained |
| Structured IaC | `structured_iac` and `structured_iac_batch` → HCL2/Lark, PyYAML/JSON, Dockerfile rules; old bounded child was not an OS boundary | Same isolation policy, 384 MB / 10 CPU seconds / 15 wall seconds; 100-file/2 MB partitions, 512 KB/file and 8 MB output retained |
| Python | `engine.python_analysis`, `quality.metrics/structure`, `flows.python_flows`, `finding_identity.annotate/python_index`; AST/tokenization and flow/identity previously in application process | Native observations run in contained 100-file/2 MB partitions; final identity also crosses boundary. 512 MB / 25 CPU seconds / 30 wall seconds and 16 MB output provide new explicit bounds. Direct installed public adapters use the same worker |
| Manifests | `baseline.inventory`: npm JSON, TOML, Maven XML and requirements/Yarn/pnpm/Gradle text parsing in application | Contained bounded manifest partitions; original symbolic/non-executing semantics retained |
| Import component metadata | `repository_store.capture` parsed component/package JSON in application | JSON parsing crosses boundary before component/name validation and persistence |
| Documentation/OpenAPI | Regex declaration extraction and OpenAPI JSON in `engine.analyze` | Contained declaration/JSON adapters; original 32 MB/2,000-document/1,501-candidate limits retained |
| Coverage uploads | LCOV/XML parser via `quality_api` and CLI; XML was in application | Entire report parsing in contained worker; coordinator supplies counts/paths, not whole source blobs. Original 1 MB report/100,000-line limits retained |
| Parent IPC/cache | Helper JSON packets, persisted own encrypted checkpoints/cache JSON | Helper IPC uses bounded pure-Python JSON scanning, depth/node caps and exact path/hash checks. Persistence envelopes, HTTP/framework JSON, trusted configuration and crypto remain coordinator TCB |
| ZIP/zlib intake — **OPEN** | `engine.read_zip`, `repository_store.archive_items`, encrypted seekable spool and provider ZIP intake still parse archive structures/decompress in coordinator | Existing path/count/ratio/byte bounds remain, but they do not contain a ZIP/zlib exploit. A separate bounded streaming archive adapter is still needed. This prevents closing overall SEC-002 |
| Global aggregation | Profile/quality/gate calculations, graph relationships, cryptography, authorized source reads and database writes | Remain trusted coordinator operations on typed observations/metadata. They have no parser subprocess credentials; global memory remains SCALE-001 |

The source/report containment claim does not include a compromised kernel, Python interpreter/core primitives, compromised trusted bootstrap/runtime code, arbitrary operator-installed plugins, HTTP framework vulnerabilities, archive intake or the coordinator's persistence/crypto layer. Raw-source parsers are separated from these explicitly named trusted components; no blanket all-parser isolation claim is made.

## Selected Linux contract

Linux defaults to `PROJECTTRACE_PARSER_ISOLATION=required`. Production rejects `development` mode and non-Linux fallback at parsing entry. Workers start with `-I -B`, a minimal fixed environment, root working directory and closed inherited descriptors. Imported source never determines executable/module, filesystem allowlist or environment.

The trusted bootstrap loads only installed parser code/resources before reading stdin. It does not import database/API/worker-service modules or inherit their credentials. HCL's default writable pickle/Lark cache is replaced with the identical grammar built without a filesystem cache. No source-dependent operation runs before controls are installed.

Landlock ABI **3 or newer** handles filesystem rights through TRUNCATE. Only installed parser/runtime files and required resources are readable; all filesystem writes/exec rights are denied, and there is no writable temporary directory. A seccomp **allowlist**, default EPERM, permits required memory/stdio/read-only runtime operations and three read-only prctl queries. Socket/network, fork/clone/exec, ptrace/process-VM/pidfd, namespace/mount, kernel privilege and filesystem metadata syscalls are not allowed. Metadata denial supplements Landlock, which alone is not a filesystem namespace. Capability effective/permitted/inheritable sets are zero, no-new-privileges is set, dumpability/core dumps are disabled, process creation is denied and RLIMIT_NPROC is zero. These controls are irreversible within the worker.

Every actual worker must demonstrate filesystem read denial, socket denial, exec denial and metadata denial, then emit its bounded policy attestation **before** reading the untrusted input packet. Readiness/cache-only native entry also launches a real probe. No configuration flag alone satisfies readiness. Unavailable controls fail closed; Linux/containers must expose Landlock syscalls and libseccomp. No elevated namespace or SYS_ADMIN capability is requested.

Resource limits remain per helper and parent wall deadlines terminate only the owned process group. Parent pipe draining bounds stdout in memory and discards stderr; a flooding child cannot allocate unlimited parent output. Completed, scoped per-file packets can survive a later interruption, but unfinished files have partial diagnostics and no affirmative observations. Malformed/scope-invalid/unattested output is rejected. Packet replay cannot cross input paths or substitute source hashes. Ordinary parser syntax errors remain explicit partial/invalid coverage, rather than successful empty results.

Production analysis failures retain encrypted input and use a sanitized `PARSER_ISOLATION_*` diagnostic without publication. Coverage import failure is invalid/unavailable, never fabricated zero or successful coverage. Policy/version is included in parser signatures, invalidating old uncontained observation/checkpoint reuse while preserving historical snapshots. Cache hits retain existing no-source-read behavior where structural identity is already complete. Child component timings are measured and merged; overlapping helper/host durations are not added as wall time.

## Supported environments and prerequisites

- Supported enforcement implementation: Linux x86-64/aarch64, Landlock ABI 3+, seccomp filtering, libseccomp.so.2 and an immutable, secret-free installed runtime. Only actually executed architectures can be called qualified; current CI tests x86-64.
- Kernel/LSM and any outer container seccomp policy must allow Landlock creation/add/restrict calls and installation of a tighter seccomp filter. Missing, disabled or blocked facilities are failures, not permission to run unrestricted.
- Docker installs libseccomp2. The dedicated job additionally runs the built non-root image read-only, with network disabled, capabilities dropped, no-new-privileges and a PID cap, and proves a sentinel readable by the application cannot be read by its parser child. This is a runtime acceptance check, not merely a build.
- Windows/non-production development may explicitly use `PROJECTTRACE_PARSER_ISOLATION=development`; status is DEVELOPMENT_UNCONTAINED. Windows Job Objects/POSIX limits do not claim filesystem/network equivalence. Linux development without a supported kernel must make that explicit opt-in; production refuses it.
- Operator secrets, uploads, other tenant objects and writable storage must never be placed inside installed parser/runtime allowlist directories. Those directories must not be tenant writable. Parent application/coordinator compromise is outside this process boundary.

This coding host returns ENOSYS for Landlock and rejects nested user namespaces. Local security enforcement is therefore **NOT QUALIFIED**. Local development-mode regression results are algorithm evidence only. Dedicated GitHub/Linux and built-container evidence must actually pass before claiming those environments work.

## Executable acceptance and evidence

`integration_tests/test_parser_isolation.py` is a required, non-skipping Linux job. It uses ProjectTrace-owned probes, not repository scripts: inaccessible sentinel read/write, metadata and proc denial, outbound/loopback/metadata-network denial, exec/fork denial, minimal environment, concurrent tenant sentinels/output separation, CPU/memory/wall/output exhaustion, crash/malformed packets, normal semantic equivalence to the baseline and parent-AST/cache/determinism checks. `scripts/parser_isolation_probe.py` runs the image contract. Run/head/artifact URLs and actual counts are recorded in draft PR #3 after execution, including any failed attempts.

The existing broad unit/algorithm CI job explicitly uses development mode for in-process instrumentation tests. Browser and all four real broker acceptance cases use required mode, exercising actual application imports, publication, auth drift, history and recovery under containment. A separate required security job supplies actual kernel enforcement and compatibility evidence. No security acceptance is skipped because a runtime is unavailable. Existing ten private-fixture browser and two Windows backend skips remain separately explained.

Performance acceptance records measured wall times for identical owned multi-language/IaC/manifest input in development and required modes in `sandbox-evidence-<run_id>/overhead.json`; no representative throughput or large-repository capacity claim follows from that small fixture. Bootstrap, process IPC and final identity add overhead; source bounds and existing helper limits are not relaxed to conceal it.

Primary mechanism references: [Linux Landlock](https://docs.kernel.org/userspace-api/landlock.html) and [seccomp filtering](https://docs.kernel.org/userspace-api/seccomp_filter.html). The latter explicitly warns that syscall filtering alone is not a sandbox; filesystem and environment/descriptor restrictions are part of this combined contract.

## Residual release gates

SEC-002 is **partially implemented, pending qualification**, and cannot be marked fully closed while the ZIP/zlib coordinator exposure remains. Linux containment tests do not establish Windows equivalence, runtime/TCB integrity, kernel exploit resistance, side-channel isolation or immunity to fabricated semantic results from a compromised parser. Parser output remains bounded/scoped data, not proof of correctness.

SCALE-001 global-memory containment, representative rule precision, default broker visibility/beat/failover/load, shared-NAT capacity, private Administration/Learning/large/static fixtures and production TLS/providers/object/key/database recovery remain open. Preserve PR #1/#2 and schema 0025. Complete the remaining archive boundary before a blanket SEC-002 release verdict; SCALE-001 remains the next separate global-analysis milestone.
