# Correlation performance final validation

Date: 2026-10-09. Continues `REPOSITORY_TIMEOUT_ROOT_CAUSE_AND_RECOVERY.md` and the earlier correlation investigation. The previous correlation report is retained unchanged in `docs/history/CORRELATION_PERFORMANCE_FINAL_VALIDATION_before_release_2026-10-09.md`; it concerns a different earlier tenant/job and is not reused as evidence for this incident.

**Decision: PASS for the current unchanged OpenMetadata retained-inventory full-analysis retry on this local hardware.** Two independent full constructions published valid PARTIAL snapshots within both the existing 900-second budget and the 720-second target. **Complete product/production readiness remains BLOCKED**, as documented in `PROJECTTRACE_FINAL_STABILITY_AND_RELEASE_VALIDATION.md`.

## Exact input, environment and reproduction

Product: `C:\Users\sai krishna\OneDrive\Desktop\ProjectTrace`. Windows 11 10.0.26300, Intel Core 5 120U/12 logical processors, 16,806,244,352 bytes RAM, Python 3.14.3, SQLite 3.50.4/SQLAlchemy 2.1.3. SQLite WAL, foreign keys and synchronous durability remain enabled. A single local analysis writer is admitted; helper maximum remains two. The database is in a OneDrive Desktop path; a filesystem contribution is possible but was not separately proven.

Current tenant `c1d9f579-bdd2-4d2b-b22f-a2020aa4a2dc`, repository `4f7304f9-c355-467f-8799-785e74b83cdf` (`data`), job `03382b0a-2de5-4d9b-a8dc-3097c129616e`, retained inventory `98db76fd-aadf-4522-99d8-46a5b36ab5e3`. The original enabled submitting user and repository grant were verified; retries used the ordinary bounded worker lifecycle. The earlier exhausted job was not reset.

Archive SHA-256 `027615f80245c4534f4af0270951ad7dc0418928440c5332522b46103ddfa914`; 157,126,481 compressed bytes, 330,420,155 expanded bytes, 21,636 inventory files. Input, analysis options, source digests, parser/rule behavior and 900-second budget were unchanged. No provider refetch, imported code execution, package installation, build or infrastructure execution was used.

The first measured normal retry failed; the second normal retry succeeded in the installed database. The repeat used a consistent **pre-repair backup**, in which the incident was failed with retry count zero and had no successful incident snapshot. That private copy was migrated to 0018; original encrypted blobs were accessed through a read-only overlay and new outputs were private. The repeat used the ordinary worker and constructed/persisted the entire graph. It did not return an existing snapshot or change the installed retry budget. Copy/migration time (94.71574 seconds for the prepared 7,896,842,240-byte copy) and old ZIP capture are outside analysis wall time.

Private measurements: `C:\Users\sai krishna\Documents\Codex\2026-10-04\pr\work\release-stability`. Principal receipts are `current-large-incident.json`, `measured-retry-1.json`, `record-key-benchmark.json`, `measured-retry-2.json`, `measured-full-repeat.json`, `large-results-consistency.json` and `typed-publication-consistency.json`.

## Stage timings: the entire 900 seconds was not correlation

| Stage seconds | Initial durable failure | Measured old-key retry | Corrected installed retry | Independent full repeat |
| --- | ---: | ---: | ---: | ---: |
| VALIDATING | 1.456660 | 2.630375 | 2.083571 | 2.203687 |
| PARSING | 0.096639 | 0.143206 | 0.087511 | 0.082401 |
| ANALYZING | 63.496602 | 90.979710 | 61.982571 | 51.060520 |
| EXTRACTING_CLAIMS | 5.473106 | 52.192754 | 23.726806 | 2.899060 |
| VERIFYING | 13.170771 | 54.401743 | 17.550916 | 12.209077 |
| BUILDING_EVIDENCE | 24.036328 | 111.656360 | 16.397787 | 14.241827 |
| CORRELATING | 824.110844 | 588.732813 | 440.045867 | 192.883544 |
| FINALIZING | Not reached | Not reached | 0.001623 | 0.000895 |

Initial stored failure was 931.852740 seconds; first measured retry stored 900.741750 seconds. A budget check records overruns after a bounded operation returns, rather than providing hard preemption of every SQL/file operation. The normal stages contain inclusive component timers; nested SQL/flush and component wall times must not be added as separate pipeline stages.

| Whole-call measurement | Old-key retry | Corrected installed | Independent full repeat |
| --- | ---: | ---: | ---: |
| Operator wall seconds, including completion/cleanup | 911.051712 | **663.671952** | **288.691365** |
| Worker resource wall seconds | 908.395505 | 661.807239 | 287.307326 |
| Stored pre-final-commit duration seconds | 900.741750 | 561.884230 | 275.589550 |
| Parent CPU seconds | 671.062500 | 223.390625 | 193.250000 |
| Sampled helper CPU seconds | 12.281250 | 9.515625 | 8.984375 |
| Parent lifetime peak GiB | 2.623 | 4.715 | 5.117 |
| Published state | FAILED | PARTIAL | PARTIAL |

The stored duration is captured before final commit/cleanup and underreports full completion. The installed run spent approximately 102 additional seconds after that measurement; SQL commit was also visible in coarse stack samples. Full call wall is the acceptance clock. Both successful runs meet the budget even with that tail included.

All runs had 18,756 parser-cache hits and 103 misses; 23 helpers launched and one active helper was observed. Sampling at 100 ms can miss short-lived helpers/instantaneous peaks; parent CPU includes the observer. Desktop/OS cache and storage path differ between installed and private replay. Therefore these numbers prove repeated measured completion but do not isolate every source of the wall-time variance or establish a large cold-cache SLA.

## Dominant bottleneck and controlled proof

The initial failure had completed finding correlation (113.539096 seconds), history (2.693863), artifact graph (28.844491) and configuration graph (4.883878); function graph had not completed. The measured old-key retry likewise failed before function graph completion. Its SQL insertion/flush samples dominated the in-progress graph work; artifact SQL was 78.4773 seconds and incomplete function SQL already 112.4707 seconds. This was not proof of a parser hang or a finding-history root cause.

| Inclusive correlation component seconds | Old-key retry | Corrected installed | Independent repeat |
| --- | ---: | ---: | ---: |
| FINDING_CORRELATION | 214.671269 | 52.646442 | 25.352212 |
| FINDING_HISTORY | 14.039044 | 3.412317 | 2.946673 |
| ARTIFACT_GRAPH | 129.217331 | 15.147657 | 13.118620 |
| CONFIGURATION_GRAPH | 33.811915 | 6.932295 | 6.101838 |
| FUNCTION_GRAPH | Incomplete | 319.432084 | 105.358021 |
| OWNERSHIP_GRAPH | Not reached | 12.725507 | 7.512178 |
| POLICY_PROJECTION | Not reached | 12.118039 | 16.992730 |
| IMPACT_GRAPH | Not reached | 4.976304 | 4.108097 |

The repaired function graph still dominates: exactly **398,272 rows**, 1,594 bounded flushes (maximum 250 rows), 8,804 SQL calls. Installed SQL cursor time was 269.434422 seconds and inclusive flush wall 281.539534 seconds; repeat SQL was 61.950579 seconds and flush 73.110488 seconds. Maximum flushes were 38.688863 and 32.662596 seconds. Storage stalls remain real; no claim is made that all correlation cost has disappeared.

To isolate key/index behavior, six counterbalanced **rollback-only** runs inserted the same 10,000 graph Records (5,000 nodes and 5,000 edges) into an exact private large mirror with 555,532 existing Records. Payloads, indexes, ORM tenant/FK guards, 250-row batches, 80 SQL calls and the existing 32 MiB SQLite cache were identical. The customer database was untouched.

| Storage identity scheme | Trial 1 wall / SQL s | Reverse trial wall / SQL s |
| --- | ---: | ---: |
| UUID4 primary plus independent UUID4 implicit natural key | 30.814896 / 28.367495 | 13.696623 / 11.355726 |
| UUID7 primary, random implicit natural key | 7.883933 / 5.029145 | 1.891558 / 1.185560 |
| UUID7 primary reused as implicit natural key | **1.378443 / 0.484756** | **0.709918 / 0.267309** |

This controlled comparison proves avoidable random B-tree insertion/index churn in two storage keys. OS cache warming affects absolute times, but the reverse ordering retains the advantage. Full pipeline changes in claims/evidence reads and incidental desktop/storage variation are not all attributed to this one intervention.

Measured slowest cold-miss file operations on the corrected installed run included Java `BaseEntityIT.java` Tree-sitter 0.698110 seconds, `TestCaseResourceIT.java` 0.389753 seconds, YAML cache action post-processing 0.362250 seconds, and Java `TaskResourceIT.java` 0.355311 seconds. Cached-file parser times were not remeasured. These timings and retained parse diagnostics do not explain hundreds of seconds of graph SQL.

## Smallest architectural correction and preservation

`backend/record_identity.py` generates portable RFC 9562 UUIDv7 storage IDs: 48-bit time and 74 CSPRNG bits, correct version/variant, no MAC/host/tenant/source content. Ordering within a millisecond is random; clock rollback affects locality, not authorization or semantic identity. `backend/domain.py` uses it for newly added Records and reuses it as the default implicit natural key. Explicit natural keys, deterministic semantic keys/fingerprints and existing Record IDs remain unchanged. Other entity UID behavior is retained.

Earlier deadline/lease checks, graph batches, cache lookup indexes, encrypted inventories, parser checkpoints, history reconciliation and publication guards remain. The snapshot, typed projections and small read projection commit atomically. No partial graph publication, cross-tenant bypass, larger timeout, extra analyzer concurrency, deleted snapshot or reduced declared scope was introduced.

Installed new snapshot `01a12093-bcc9-7dbc-9ac8-320abfb01c18`; independent new snapshot `01a1209d-c8cb-7295-bb43-6a728adcca92`. Both produced identical canonical claims/findings, coverage and warning content, graph classes and relationship distributions. Counts: 1,500 claims (934 verified), 7,904 findings (1,368 critical/high), 18,859 evidence files, 2,090 dependencies, 231,228 nodes and 289,745 edges. Duplicate current finding fingerprints and missing/foreign graph endpoints are zero.

The old snapshot `9fc9a751-0ef7-4673-b437-93ea40768cfd` has one extra first-baseline policy node (`Quality: baseline`) because its base is null. The new retry uses that old snapshot as base and legitimately omits the first-baseline node. The old rows are unchanged; this difference is not silently treated as graph equality or lost evidence. Current typed history has 8,290 finding occurrences including historical/resolved rows, 6,843 quality occurrences, one quality analysis, 133 cloud assets and one snapshot inventory.

Coverage: 21,636 discovered; 18,859 native scan; 14,567/15,669 source parsed (92.967005%). Retained states: unsupported 1,083; partial 17,671; policy ignored 1,475; size skipped 32; generated 1,058; parse failed 33; binary 189; vendor 95. Warnings: 105; claim extraction cap 1,500; runtime UNOBSERVED. Language distribution (files/parsed): TypeScript 7,866/6,820; Java 4,609/4,598; Python 3,054/3,037; JavaScript 112/112; SQL 342/0; Shell 60/0; Make 3/0; CloudFormation 17/17; Compose 29/26; Dockerfile 26/16; Kubernetes 41/39; other text/binary 4,799/0; unknown 678/0. A valid PARTIAL result is not promoted to full semantic coverage.

## Tests, staged benchmarks and recovery

Final backend suite: **480 passed**, no skips, 620.12 seconds, including private real PostgreSQL integrations and bottleneck-specific storage identity, correlation bounds, indexed-query, tenant paging and failure/recovery tests. Frontend: **35 passed**, production build succeeded, final Ruff checks passed. The comprehensive Chromium acceptance suite had **15 passed** after restart (198.481017 seconds operator wall) and **15 passed again** after a clean API/UI restart (257.832151 seconds). No imported project source was executed by these tests.

| Static files, ten functions each | Cold wall s | Warm wall s | One-file change wall s |
| --- | ---: | ---: | ---: |
| 20 | 0.696751 | 0.296651 | 0.481038 |
| 100 | 1.948301 | 3.271518 | 6.304806 |
| 500 | 9.741847 | 6.684950 | 31.222108 |

All fixture pipelines completed and declared source parsing was 100%. Cold means no product parser cache; OS cache was not cleared. Changed-file runs reused N−1 artifacts/read one changed source blob, but recomputed global history/graph work; the 500-file changed run had 15.24025 seconds SQL time. End-to-end incremental speedup is not claimed.

An owned 500-file worker was killed before publication after durable native checkpointing; the ordinary private expired-lease path recovered once, reused 500 artifacts, published one snapshot and verified audit in 23.489191 seconds. Installed API/worker/Beat restart tests retained jobs/input/key state. Preservation compared 1,173,595 old immutable Records and the existing typed/history/grant/audit tables: zero missing/changed; old 64,563 encrypted files remained, 100 decrypt/hash samples passed, 21 audit heads verified and final SQLite FK check had zero violations.

## Remaining uncertainty and release limitations

The original warm-input timeout is **fixed in the validated local scope** with two full completions below 720 seconds. It is not a general cold-cache, end-to-end large-import or maximum-scale guarantee. Large cold parsing was not freshly qualified. Final commit/cleanup is outside the legacy stored-stage duration; acceptance uses whole-call wall.

Peak 4.715/5.117 GiB is incompatible with the current 1 GiB Compose worker limit; limits were not raised to hide that mismatch. Parent memory is not yet proven bounded to a deployable envelope. Correlation still holds global state and one atomic transaction; parser recovery does not provide durable mid-graph continuation. CPU/helper utilization and SQLite stalls remain uneven. Concurrent large analysis under resource pressure remains unqualified.

Realistic further architecture is compact/disk-backed graph construction with deterministic bounded stage units, durable generation checkpoints, idempotent writes and a fenced atomic published-generation switch. PostgreSQL indexed bulk publication is another deployment option to benchmark. Those changes must preserve history/relationships and be proven under the intended memory/CPU envelope, rather than inferred from this local success. Prior full-product security/sandbox, synchronous large-ingestion, independent accuracy and operational qualification gaps also remain open. Complete production release decision remains **BLOCKED**.
