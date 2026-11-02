# Existing graph and workspace ordering contract — 2026-10-27

This is a read-only contract inventory for the full-membership scalar-key
experiment. It does not authorize a new ordering policy, schema migration, or
production change. Original rows, expected sequences and old prototype evidence
remain unchanged. SCALE-001 remains NOT QUALIFIED.

`ordering-evidence.json` contains the complete SQL, binds, returned rows, hashes,
EXPLAIN plans, actual index definitions and source-database hashes for eight
query variations on the original baseline and the three rejected v1 databases.
All connections were `mode=ro`; no ANALYZE, DML, DDL or PRAGMA setting changes
were performed. SQLite runtime: 3.50.4. These are owned Windows fixtures.

## Contract levels

1. Explicit ORDER BY is part of the query contract. Preserve its exact
   expressions, direction, collations, tie-breaking and placement relative to
   LIMIT/OFFSET, window ranking and UNION deduplication.
2. The absence of ORDER BY gives SQL no portable sequence guarantee. Nevertheless,
   the requested compatibility gate includes the currently observable sequence:
   compare complete results to the frozen original fixture, rather than sorting
   them, replacing expectations, or assuming row-set equality is sufficient.
3. Incidental ordering is plan-specific. Do not impose one graph-target ordering
   on every derived query: additional filters can switch the original access
   path and its returned order. Preserve the original AST, full key membership,
   row identity and relevant access paths where possible; validate actual plans
   and results, including after ANALYZE, rather than claiming a universal SQLite
   order from one fixture.

## Query inventory and observable behavior

| Source / operation | Existing ordering | Compatibility requirement |
|---|---|---|
| `backend/domain.py:204`, `snapshot_record_query` | No ORDER BY; fixed tenant/repository plus nested-scope OR top-level snapshot ID | Preserve raw mixed sequence, including snapshots and historical top-level graph-shaped fields |
| `domain.py:215`, `scoped_snapshot_records(core=False)` | Direct list materialization of the mixed query | Do not treat the resulting list as a set |
| `scoped_snapshot_records(core=True)` | Adds claim/finding/dependency/drift kinds; still no ORDER BY | Preserve filtered sequence and complete content; this is not interchangeable with the unfiltered plan |
| `domain.py:231`, impact seed evidence | Adds evidence kind/path filter and LIMIT; no ORDER BY | Existing traversal determines which bounded seeds are retained; changing order can change membership after LIMIT |
| `domain.py:264`, impact edge expansion | `Record.id ASC`, then limit | Preserve ID order and bounded selection before materialization |
| `domain.py:276`, impact node hydration | Adds `Record.id IN (...)`; no ORDER BY | An ID seek can return a different order from a target-index prefix scan; preserve actual filtered behavior |
| `domain.py:667,670,1778,1795`, baseline/head consumers | Use mixed/core readers and further kind predicates | Preserve raw rows, downstream ordering and resulting complete analysis fingerprints |
| `backend/graph_api.py:34`, snapshot selection | `created_at DESC, id DESC`, LIMIT 1 | Complete explicit tie-breaking; keep authorization and generation visibility before selection |
| `graph_api.py:81`, node page | `kind ASC, id ASC`, OFFSET/LIMIT | Stable page order across kinds; unique ID breaks ties |
| `graph_api.py:126`, neighborhood edges | Source/target SELECTs combined with UNION; outer `id ASC`, OFFSET/LIMIT | UNION removes duplicate/self-edge identifiers before pagination; preserve both endpoint seeks and exact order |
| `graph_api.py:130`, linked neighborhood nodes | `id IN (...)`, kinds/scope/tenant predicates; no ORDER BY | Directly returned as the HTTP `nodes` array, so incidental order is observable even though not portable |
| `backend/workspace_read.py:72`, latest jobs | ROW_NUMBER per repository ordered by coalesced started/queued/created timestamp DESC, then ID DESC | Preserve window input/ranking, shared ranked-subquery identity and position=1 join; the unordered outer results become a repository-keyed dict |
| `workspace_read.py:100`, grouped summary counts | GROUP BY within scoped SELECT/UNION ALL chunks | Group row order is not a page contract; all grouped values/counts and tenant ownership must match |
| `workspace_read.py:177`, bounded previews | Each branch `created_at DESC, id DESC`, LIMIT 5; Python merges/sorts the same keys and hydrates in that preserved sequence | Preserve branch-local limits, tie-breaking, candidate merge order and explicit final hydration list |
| `workspace_read.py:207`, `page_query`; `backend/main.py:858–862` caller | Count removes ORDER BY; result page uses `created_at DESC, id DESC`, OFFSET/LIMIT | Keep count/page filter equality; explicit page order and boundary membership must match |
| `backend/main.py:707` legacy workspace read | `created_at DESC` only with LIMIT 5001 | Equal timestamps lack a complete explicit tie-breaker; do not silently add ID order or assume incidental ties are unobservable |

The rejected recursive SELECT rebuild failed five workspace tests because it
duplicated the single ranked alias referenced by both JOIN and the position
predicate. SQL contained `AS anon_1` twice in the same FROM and failed with
`ambiguous column name: anon_1.position`. Scalar-key reader work must avoid
cloning/rebuilding that query structure or touching immutable loader/security
options.

## Measured original traversal and filtering counterexamples

The original `ix_records_graph_target` has six index_xinfo entries, all ascending
with BINARY collation: organization ID, repository ID, kind, two expression keys,
then the auxiliary hidden rowid. The two expressions are exactly:

```sql
CAST(JSON_EXTRACT(data, '$."snapshot_id"') AS VARCHAR)
CAST(JSON_EXTRACT(data, '$."target"') AS VARCHAR)
```

`records.id` is a VARCHAR primary key, not INTEGER PRIMARY KEY and not the hidden
rowid. The hidden integer rowid is the final tie-breaker of this index traversal.
Replacing it with lexical ID order changes equal-key legacy results.

| Original fixture variation | Count | Actual original plan / sequence |
|---|---:|---|
| Unfiltered mixed query | 179 | graph_target tenant/repository prefix; SHA `e8bc1be8bbce71eb2e0cb87964e1fb8c761ede4ca9f214c2986ec3821eea7fd6` |
| Extra `version >= 1` | 179 | Same plan, same exact hash; this predicate excludes no fixture rows |
| Extra ID-IN of edge0001, edge0011, node0000 | 3 | `uq_records_checkpoint_scope(id,org,repo)`; sequence edge0001, edge0011, node0000; SHA `a6c74d9ff0c5ea1362ed801e2eb538a3e4aa0f0693e74fd15d9015dd99a5a22e` |
| Path LIKE `owned/%` | 120 | graph_target tenant/repository prefix; SHA `b3f05a7e26d191a5ababb6e56ae60c5f6a7cb3eec91cc84a0f8f9b2204808174` |
| Core-kind IN filter | 72 | graph_target tenant/repository/kind prefix; SHA `18dc5b36f7782ad4b22833c4258ffba162a65e89acf879c58b6f909b71d124e8` |
| Mixed LIMIT 1 | 1 | Same graph_target prefix; node0001 is selected |
| Mixed OFFSET 49 LIMIT 7 | 7 | Same graph_target prefix; first IDs edge0011, edge0012, edge0023 |
| Mixed explicit kind/ID order | 179 | Exact explicit-order result is identical across all four original/rejected databases |

Rejected plain/validated partial indexes change 52 positions of the unfiltered
and version-filtered 179-row sequences, despite identical complete row sets.
They change all seven page positions at OFFSET 49 and also page membership.
CASE changes eight legacy snapshot positions because it substitutes NULL for
their actual top-level graph keys. Full membership means retaining those real
snapshot keys, not retaining rows while substituting placeholder keys.

The preceding recovery experiment's owned ANALYZE matrix preserved its 62 frozen
sequences before and after ANALYZE. That is useful prior evidence, not a guarantee
for a new scalar schema: the new schema needs its own before/after statistics
and row-sequence comparison. `reverse_unordered_selects=ON` previously reversed
the original mixed/core sequence; this demonstrates the incidental nature of
the original ordering and does not authorize modifying expectations.

## Types, NULL, collation and legacy scope

- Original graph keys are VARCHAR CAST results. Numeric/bool values become the
  original SQLite text representation; NULL/missing values remain NULL, and
  object/array values have SQLite JSON serialization semantics. Scalar columns
  or projection extraction must preserve those results and TEXT comparison
  affinity, not just Python-looking values.
- CASE has no TEXT affinity by itself even if its THEN arm is a VARCHAR CAST.
  The rejected recovery proved the danger: `CAST('1' AS VARCHAR)=1` is true,
  but CASE-wrapped text compared to integer 1 is false unless the outer CAST is
  retained. A scalar candidate must test int/float/bool/string binds, NULL and
  explicit NOCASE conditions against the original expression behavior.
- The observed target traversal sorts NULL first in ascending order and uses
  BINARY, not locale-aware Unicode folding. Decomposed/composed accents, sharp-S,
  non-ASCII text, embedded NUL and equal keys with IDs disagreeing with rowids
  belong in frozen-sequence and pagination tests.
- Mixed scope is nested `scope.snapshot_id OR snapshot_id`. Edges generally use
  the top level; core observations generally use nested scope. Historical rows
  can use either or both. Do not replace the mixed predicate with only one path
  or exclude snapshot records.
- Tenant/repository columns and publication/generation visibility remain the
  authorization authority. Forged JSON scope metadata must not substitute for
  row ownership. Preserve all predicates and opaque loader criteria unchanged.
- Legacy malformed JSON rejection/error precedence, duplicate JSON fields,
  scalar roots, JSON5 and supported JSON-as-BLOB/JSONB behavior need the existing
  229-case corpus. Do not replace JSON1 extraction with a narrower JSON validator.

## Implications for a scalar-key prototype

A full-membership candidate should keep every original index key value and row
identity for all kinds, including snapshots. Scalar fields must not truncate or
pretend to be fixed-size: a legacy source/target/class value can itself be a
large string/object/array. Avoid copying the whole snapshot merely to retain a
handful of graph keys. Full membership is necessary but not sufficient: physical
layout, statistics, affinity and predicate eligibility can still change plans.

Prefer compiler-local emission for the existing `IndexedText` fixed paths over
any generic SQLAlchemy AST rebuild. That keeps aliases, ranking, shared joins,
security options, GROUP BY, UNION and pagination structures intact.

Do not automatically map ordinary `Record.data[...].as_string()` bound-path SQL
to scalar columns. The original mixed reader uses bound JSON paths and therefore
cannot use the original expression indexes beyond their ordinary prefix.
Mapping that predicate to scalar columns can newly enable OR/multi-index seeks
and change incidental order. It is reasonable to keep this raw bound-path SQL
unchanged while mapping only the already indexable fixed-path `IndexedText`
queries, then verify exact results/plans. This retains the baseline read-side
JSON cost rather than introducing a full-row sorter.

For alias-safe fixed-path emission, require actual Record.data proxy ancestry,
approved developer-defined paths and matching string semantics. Leave other
models' JSON, JSON-valued or integer-valued extraction, and caller-named/runtime
path binds alone. Use the compiler's actual table/alias identity; do not invent
alias names or new FROM clauses. Tests must prove that compiler changes apply
only to the owned candidate engine and are restored at teardown.

Ordinary metadata columns with AFTER triggers are a small, testable alternative
but may write the large record twice. Generated STORED compact metadata plus
virtual scalar keys could avoid repeated full parsing, but cannot be added with
SQLite ALTER ADD STORED and may change INSERT/SELECT-star arity; the frozen
duplicate-insert error contract must be checked. A projection table avoids
another large payload write, but joins/correlated scalar reads can change rowid
ownership, row counts, traversal and selective endpoint plans. None is assumed
optimal or safe without measurement.

No universal deterministic order is newly promised here. Acceptance is literal
compatibility with the frozen expected sequences plus the known filtered,
ranked/workspace and HTTP shapes. A separately approved new stable ordering
policy would be a different contract decision.
