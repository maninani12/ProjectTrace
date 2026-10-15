# Requirements, evidence and acceptance register

Date: 15 October 2026. Overall release: **BLOCKED**. Historical reports remain preserved; current results must be read from the latest generation/learning handoff and its raw test artifacts. Overlapping test selections are not summed.

| Requirement | Implementation | Evidence / acceptance |
|---|---|---|
| DUR-001 private incomplete output | Generation ownership and default reader predicates | `test_generations.py`: stage interruption, aliases/counts/projections, API 404s |
| DUR-002 resumable dependencies | 14 signed receipt boundaries and encrypted chunks | Every boundary restarted in a fresh Session; earlier ciphertext/digests preserved |
| DUR-003 fencing and cancellation | Fenced batch/validation/promotion | Replaced token, cancelled claim and revoked repository reject promotion |
| DUR-004 duplicate prevention | Deterministic rows, occurrence/audit IDs, graph deduplication, pointer CAS | Duplicate graph before batch commit; duplicate content reuse; two PostgreSQL generations race and exactly one publishes; old histories retained |
| DUR-005 atomic publication | One visibility/pointer/job transaction | Precommit failure remains private; lost acknowledgement resolves committed state |
| DUR-006 source/version integrity | Source hashes/blobs, analyzer/parser identity, native profile lineage | Corrupt source/receipt/reference/count tests; changed profile rejects promotion |
| DUR-007 tenant relationships | Composite generation/job/Record/audit and learning FKs; migration 0023 preserved | SQLite direct-SQL negatives and real PostgreSQL scope tests |
| DUR-008 bounded persistence | 250 Record batches, bounded keyset validation, encrypted chunk/context limits | Existing flush/lookup assertions retained; real archive counters/profile |
| DUR-009 complete bounded global memory | Partial: bounded ORM state and indexed correlations; global collections remain | **NOT CLOSED**; separately pinned OpenMetadata captures 21,636 files / 7,744 parser artifacts but cold verification raises MemoryError under a 768 MB process-tree commit ceiling; no public pointer. Exact historical ZIP also remains unqualified. |
| REL-001 real worker crash | Actual owned Python process exit inside stage/after receipt/after validation | Different recovered lease token; no public snapshot before promotion |
| REL-002 database interruption | Real PostgreSQL backend termination before promotion | Private VALIDATED generation restored in fresh Session |
| REL-003 real broker recovery | Existing Celery configuration retained | **NOT_TESTED here**; no local Redis/Docker/WSL environment |
| LEARN-001 new-hire mode | Published target knowledge, role/skills/objectives/assessments/reviews | API and browser workflow against pinned repository evidence |
| LEARN-002 internal transfer | Independently authorized prior/target projects and explicit comparison | API and browser workflow; prior grant revocation denies reads |
| LEARN-003 independent review | Distinct participant/mentor/manager, versioned transitions | Impersonation/self-review and premature completion rejected |
| LEARN-004 source refresh/history | New revision after source publication; earlier completion retained | Real second source snapshot in API regression |
| LEARN-005 privacy/access | Encrypted responses/notes, finite retention, features/team/repository checks | Ciphertext inspection, expiry, feature denial, unassigned-user and tenant negatives |
| LEARN-006 frontend confidentiality | Organization/user/access-version query keys | Organization-switch regression; obsolete responses discarded |
| SEC-001 imported code safety | Static owned parsers; no repository execution/install/build | Source archive qualification records and existing parser/archive suites |
| SEC-002 parser filesystem/network isolation | Incomplete | **RELEASE GATE**; helper limits do not establish isolation |
| OPS-001 additive safe upgrades | 0024/0025 preserve existing Records; populated downgrade refuses data loss | SQLite/PostgreSQL preservation/rollback tests; QA online backup before upgrade |
| OPS-002 backup/restart | Prior real PostgreSQL restore retained; full generated SQLite/object/key restore at schema 0025 | All table counts and ordered Record/user fingerprints match; 622 source objects and all assessment/review ciphertexts decrypt; fresh API reads both completed modes for all three assigned roles; production DR not implied |
| ACCEPT-001 regressions | Full backend, frontend, TypeScript/build, browser | 599 backend passed, no failures/skips; 46 frontend passed; TypeScript/build passed; 24 distinct browser cases passed across explicit fixture/admission groups, one historical large-fixture case skipped; intermediate failed runs retained |

## Defect register for this continuation

1. Successful snapshot return values detached during cleanup: preserve successful objects and weakly detach only live private state. Existing refresh/history assertions unchanged.
2. Canonicalizing a snapshot key caused a second update: generation content-key ledger provides idempotency without rewriting the snapshot key. Original single-update assertion unchanged.
3. Duplicate graph rows after parent flush but before ownership commit: recognize pending ownership and reuse the same row; direct regression added.
4. Expired cached private objects could refresh outside loader predicates: weak ownership cleanup detaches those objects; cached-ID regression added.
5. Finding cache eviction produced individual finding reads: shared JSON working state and bounded fenced updates preserve the zero-individual-read assertion.
6. Graph duplicate lookups caused autoflush per node: pending-row lookup and `no_autoflush` preserve full 250-row graph batches; original batch-count assertions unchanged.
7. Administration-first model import caused a cycle: deferred visibility references and model-boundary registration; four fresh-process import orders tested.
8. Learning member selection only exposed the first directory page: bounded search/offset API and visible member search; regression uses more than 50 members.
9. Learning cache keys lacked organization/access context: scope-qualified keys and obsolete-response guard; organization-switch UI regression added.

Browser harness corrections (native combobox role selection and actual captured-record/upload response synchronization) and the PostgreSQL test invocation from the wrong working directory are retained as harness failures, not product defects or passing evidence. The unchanged 240/minute shared-IP admission limit requires separate qualification windows; no rate limit or success assertion was relaxed. The private QA fixture intentionally lacks demonstration accounts, so demo/workspace cases use a newly seeded isolated database. The initial profiled/unprofiled runs are distinct measurements. Test fixtures generate labelled people/reviews; automated review scores demonstrate workflow mechanics, not independently certified employee competence.

Open scale issue SCALE-001: the cold pinned OpenMetadata run reports failure at VERIFYING under the explicitly imposed local 768 MB ceiling after retaining its complete inventory and parser artifacts. Database integrity passes and no generation/pointer is published. One retained-input diagnostic retry also fails: its traceback identifies the derived metric-dictionary collection in `analyzers/code_quality/core.py:56`, reached from quality aggregation in `engine.py:1335`, while original repository observations remain resident. The retry also records subprocess reader-thread allocation failures under the same process-tree ceiling. These are failed scale experiments, separate from the 599 passing backend regressions; no full global-memory solution is claimed.
